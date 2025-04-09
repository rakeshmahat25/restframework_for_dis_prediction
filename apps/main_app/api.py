import pandas as pd
import hashlib
from django.core.cache import cache
from django.db import transaction
from django.db.models import Avg
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework import serializers
from django.db import IntegrityError, transaction
from django.db.transaction import TransactionManagementError
from django.core.exceptions import ValidationError
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from apps.main_app.models import DiseaseInfo, Consultation, Doctor, RatingReview, Patient, DoctorAvailability
from .serializers import (
    SymptomInputSerializer,
    DoctorSerializer,
    PatientSerializer,
    ConsultationCreateSerializer,
    ConsultationDetailSerializer,
    RatingSerializer,
    DoctorAvailabilitySerializer,
    DoctorAvailabilityUpdateSerializer,
    DoctorFeedbackSerializer,
    
)
from apps.accounts.permissions import IsPatient, IsDoctor
from .utils.data_loader import ML_DATA, MODEL
import logging
from django.db.models import Q
from rest_framework.pagination import PageNumberPagination

logger = logging.getLogger(__name__)


def send_notification(user_id, message):
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_{user_id}", {"type": "consultation_notification", "message": message}
        )
        logger.info(f"Notification queued for user {user_id}")
    except Exception as e:
        logger.error(f"Notification system offline: {str(e)}")



class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50

class PredictionViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsPatient]
    throttle_scope = "predictions"
    pagination_class = StandardResultsSetPagination # Add pagination class to the ViewSet

    # --- predict_disease action (keep as is, looks okay) ---
    @action(detail=False, methods=["post"])
    def predict_disease(self, request):
        serializer = SymptomInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Ensure symptoms is a list of strings if it isn't already
        symptoms_list = serializer.validated_data["symptoms"]
        if not isinstance(symptoms_list, list):
             return Response({"error": "Symptoms must be a list."}, status=status.HTTP_400_BAD_REQUEST)

        symptoms = sorted(symptoms_list)

        symptoms_set = set(symptoms)
        concatenated = "".join(symptoms)
        cache_key = f"prediction_{hashlib.md5(concatenated.encode()).hexdigest()}"

        if cached := cache.get(cache_key):
            print("Returning cached prediction") # Debugging
            return Response(cached)
        print("Cache miss, performing prediction") # Debugging

        # --- ML Prediction Logic ---
        # Ensure ML_DATA["symptoms"] exists and is a list
        if "symptoms" not in ML_DATA or not isinstance(ML_DATA["symptoms"], list):
             logger.error("ML_DATA['symptoms'] is not configured correctly.")
             return Response({"error": "Diagnosis service configuration error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        vector = [1 if s in symptoms_set else 0 for s in ML_DATA["symptoms"]]

        disease_idx = -1 # Initialize
        try:
            X_input = pd.DataFrame([vector], columns=ML_DATA["symptoms"])
            disease_idx = MODEL.predict(X_input)[0]
            disease_name = ML_DATA["label_encoder"].inverse_transform([disease_idx])[0]
            confidence = round(MODEL.predict_proba(X_input).max() * 100, 2)
            print(f"Predicted: {disease_name} with confidence {confidence}") # Debugging
        except IndexError as e:
            logger.error(f"Invalid disease index {disease_idx} from model prediction: {str(e)}")
            return Response(
                {"error": "Diagnosis service configuration error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as e:
            logger.error(f"Prediction failed: {str(e)}")
            return Response(
                {"error": "Diagnosis service unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        # --- End ML Prediction ---

        recommended_specialization = ML_DATA["disease_mapping"].get(
            disease_name, "General Physician"
        )
        print(f"Recommended Specialization: {recommended_specialization}") # Debugging

        try:
             # Ensure request.user has a patient_profile
            patient_profile = getattr(request.user, 'patient_profile', None)
            if not patient_profile:
                # Handle case where user might not have a patient profile yet
                # Option 1: Create one if needed (requires PatientProfile model logic)
                # patient_profile = PatientProfile.objects.create(user=request.user, ...)
                # Option 2: Return an error
                logger.error(f"User {request.user.id} does not have an associated patient profile.")
                return Response({"error": "Patient profile not found for user."}, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                disease_info = DiseaseInfo.objects.create(
                    patient=patient_profile, # Use the fetched profile
                    symptoms=symptoms, # Store the sorted list
                    disease_name=disease_name,
                    confidence=confidence,
                    no_of_symptoms=len(symptoms),
                    consult_doctor=recommended_specialization,
                )
                result = {
                    "disease": disease_name,
                    "confidence": confidence,
                    "recommended_specialization": recommended_specialization,
                    "prediction_id": disease_info.id,
                }
                cache.set(cache_key, result, timeout=3600) # Cache for 1 hour
                print(f"Prediction saved with ID: {disease_info.id}") # Debugging
        except Exception as e:
            logger.error(f"Database error saving prediction: {str(e)}")
            return Response(
                {"error": "Unable to save prediction result"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(result, status=status.HTTP_200_OK) # Use 200 OK for successful prediction



class SpecializationViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsPatient]
    throttle_scope = "specializations"
    pagination_class = StandardResultsSetPagination # Add pagination class to the ViewSet


    # --- RECOMMENDED DOCTORS (Corrected) ---
    @action(detail=True, methods=["get"])
    def recommended_doctors(self, request, pk):
        """
        Get paginated list of doctors with the specialization recommended
        for a specific prediction (identified by pk).
        """
        try:
            # Get the specific disease prediction instance, ensuring it belongs to the current user
            disease_info = DiseaseInfo.objects.get(
                id=pk,
                patient=request.user.patient_profile # Ensure ownership
            )

            specialization = disease_info.consult_doctor
            print(f"Fetching doctors for prediction {pk}, specialization: {specialization}") # Debugging

            # Find doctors matching the specialization (case-insensitive)
            # Assumes Doctor model has 'specialization' field and 'user' ForeignKey
            doctors_queryset = Doctor.objects.filter(
                Q(specialization__iexact=specialization) |
                Q(specialization__icontains=specialization)
            ).select_related('user').order_by('-rating', 'name') 

            # Paginate the queryset
            paginator = self.pagination_class() # Use the ViewSet's pagination class
            result_page = paginator.paginate_queryset(doctors_queryset, request, view=self)

            # Serialize the *paginated* doctors list
            # Pass context to serializer if it needs the request (e.g., for image URLs)
            serializer = DoctorSerializer(result_page, many=True, context={'request': request})

            # Return the paginated response
            # get_paginated_response structures the response with "count", "next", "previous", "results"
            return paginator.get_paginated_response(serializer.data)

        except DiseaseInfo.DoesNotExist:
            logger.warning(f"Prediction with id={pk} not found or access denied for user {request.user.id}.")
            return Response(
                {"error": "Prediction not found or access denied"},
                status=status.HTTP_404_NOT_FOUND
            )
        except AttributeError:
             # This might happen if request.user doesn't have 'patient_profile'
             logger.error(f"User {request.user.id} does not have 'patient_profile' attribute.")
             return Response({"error": "User profile configuration error."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error fetching recommended doctors for prediction {pk}: {str(e)}")
            return Response(
                {"error": "Unable to retrieve recommended doctors"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class DoctorDetailViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Provides actions related to viewing Doctor details.
    - list: (/api/v1/doctors/) Returns a list of doctors (consider filtering/pagination).
    - retrieve: (/api/v1/doctors/{pk}/) Returns details for a single doctor.
    - availability: (/api/v1/doctors/{pk}/availability/) Custom action for time slots.
    - feedbacks: (/api/v1/doctors/{pk}/feedbacks/) Custom action for feedback list.) for now in COMMENT
    """
    
    serializer_class = DoctorSerializer
    permission_classes = [IsAuthenticated]  # Adjust permissions as needed
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return (
            Doctor.objects.filter(available=True)
            .annotate(avg_rating=Avg("ratings__rating"))
            .select_related("user")
            .prefetch_related("ratings")
            .order_by("-year_of_registration")
        )
    
    def retrieve(self, request, pk):
        """Custom retrieve to add more detailed information for a specific doctor"""
        try:
            # Get the doctor with enhanced querying for detailed view
            doctor = Doctor.objects.filter(user_id=pk)\
                .annotate(avg_rating=Avg("ratings__rating"))\
                .select_related("user")\
                .prefetch_related(
                    "ratings", 
                    "feedbacks",
                    "consultations"
                ).first()
            
            if not doctor:
                return Response(
                    {"error": "Doctor not found or unavailable"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Use the regular serializer but with more context for the detailed view
            serializer = self.get_serializer(
                doctor, 
                context={'request': request, 'detailed': True}
            )
            
            # Get availability schedule for the doctor (if you have this)
            # This would need to be adjusted based on your model structure
            availability = DoctorAvailability.objects.filter(doctor=doctor)
            availability_data = DoctorAvailabilitySerializer(availability, many=True).data
            
            # Get recent feedbacks (limit to 5)
            # recent_feedbacks = doctor.feedbacks.order_by('-created')[:5]
            # feedback_data = DoctorFeedbackSerializer(recent_feedbacks, many=True).data
                
            # Combine all data
            result_data = serializer.data
            print(f"Doctor details retrieved: {result_data}") # Debugging
            result_data.update({
                'availability': availability_data,
                # 'recent_feedbacks': feedback_data,
                # Add other specific information as needed
            })
            
            return Response(result_data)
            
        except Exception as e:
            logger.error(f"Error retrieving doctor details: {str(e)}")
            return Response(
                {"error": "Unable to retrieve doctor details"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
    @action(detail=True, methods=['get'])
    def availability(self, request, pk=None):
        """Endpoint to get a doctor's available time slots"""
        try:
            doctor = self.get_object()
            # Get all available time slots for the doctor
            # This would need to be adjusted based on your model structure
            availability = DoctorAvailability.objects.filter(doctor=doctor)
            serializer = DoctorAvailabilitySerializer(availability, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error retrieving doctor availability: {str(e)}")
            return Response(
                {"error": "Unable to retrieve availability information"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # @action(detail=True, methods=['get'])
    # def feedbacks(self, request, pk=None):
    #     """Endpoint to get all patient feedback for a doctor"""
    #     try:
    #         doctor = self.get_object()
    #         feedbacks = doctor.feedbacks.all().order_by('-created_at')
            
    #         # Apply pagination
    #         page = self.paginate_queryset(feedbacks)
    #         if page is not None:
    #             serializer = DoctorFeedbackSerializer(page, many=True)
    #             return self.get_paginated_response(serializer.data)
                
    #         serializer = DoctorFeedbackSerializer(feedbacks, many=True)
    #         return Response(serializer.data)
    #     except Exception as e:
    #         logger.error(f"Error retrieving doctor feedbacks: {str(e)}")
    #         return Response(
    #             {"error": "Unable to retrieve feedback information"},
    #             status=status.HTTP_500_INTERNAL_SERVER_ERROR
    #         )



from rest_framework.views import APIView


class DoctorAvailabilityUpdateView(APIView): # Changed base class to APIView
    """
    Allows a logged-in doctor to update their availability status.

    Send a PATCH request to /api/v1/doctors/me/availability/ with:
    {
        "available": true  // or false
    }

    A PUT request will also work and perform the same action.
    """
    permission_classes = [IsAuthenticated, IsDoctor] # Must be logged in AND be a doctor
    serializer_class = DoctorAvailabilityUpdateSerializer # Good practice to define for documentation/schema

    def get_object(self):
        """Helper method to get the doctor profile of the current user."""
        try:
           
            return self.request.user.doctor_profile
        except Doctor.DoesNotExist:
            # This case should ideally be prevented by the IsDoctor permission,
            # but handle it defensively.
            logger.warning(f"Doctor profile not found for user {self.request.user.pk}")
            return None
        except AttributeError:
             # This happens if the user object somehow doesn't have 'doctor_profile'
             # Also should be caught by IsDoctor permission.
             logger.error(f"User {self.request.user.pk} lacks 'doctor_profile' attribute.")
             return None

    def patch(self, request, *args, **kwargs):
        """Handles the PATCH request to update availability."""
        doctor_profile = self.get_object()
        if not doctor_profile:
             # If get_object returned None, the user doesn't have a profile
             return Response(
                 {"error": "Doctor profile not found for the current user."},
                 status=status.HTTP_404_NOT_FOUND
             )

        serializer = DoctorAvailabilityUpdateSerializer(data=request.data)

        if serializer.is_valid():
            new_availability = serializer.validated_data['available']

            # --- Update the doctor's availability ---
            doctor_profile.available = new_availability
            # Use update_fields for efficiency if only changing this field
            doctor_profile.save(update_fields=['available'])
            # --- End of Update ---

            logger.info(f"Doctor {request.user.pk} updated availability to {new_availability}")
            # Return the updated status
            return Response({"message": "Availability updated successfully.", "available": new_availability}, status=status.HTTP_200_OK)
        else:
            # Return validation errors if input is incorrect
            logger.warning(f"Invalid availability update data for doctor {request.user.pk}: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, *args, **kwargs):
        
        return self.patch(request, *args, **kwargs)


class ConsultationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsPatient]

    def get_serializer_class(self):
        if self.action == "create":
            return ConsultationCreateSerializer
        return ConsultationDetailSerializer

    def get_queryset(self):
        return Consultation.objects.filter(
            patient=self.request.user.patient_profile
        ).select_related("patient", "doctor")

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            consultation = serializer.save()
            consultation.participants.add(request.user, consultation.doctor.user)

            return Response(
                ConsultationDetailSerializer(consultation).data,
                status=status.HTTP_201_CREATED,
            )
        except (IntegrityError, TransactionManagementError) as e:
            logger.warning(f"Duplicate consultation: {str(e)}")
            return Response(
                {"error": "Duplicate consultation detected"},
                status=status.HTTP_409_CONFLICT,
            )
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to create consultation"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"])
    def rate(self, request, pk=None):
        consultation = self.get_object()
        serializer = RatingSerializer(
            data=request.data, context={"consultation": consultation}
        )
        serializer.is_valid(raise_exception=True)
        RatingReview.objects.update_or_create(
            patient=consultation.patient,
            doctor=consultation.doctor,
            defaults=serializer.validated_data,
        )
        return Response({"status": "Rating submitted"}, status=status.HTTP_201_CREATED)


class DoctorConsultationViewSet(viewsets.ModelViewSet):
    serializer_class = ConsultationDetailSerializer
    permission_classes = [IsAuthenticated, IsDoctor]
    lookup_field = "id"
    lookup_url_kwarg = "pk"

    def get_queryset(self):
        return Consultation.objects.filter(
            doctor=self.request.user.doctor_profile
        ).select_related("patient", "doctor")

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        consultation = self.get_object()
        if consultation.status != "requested":
            return Response(
                {"error": "Consultation must be in requested state"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Transition will auto-save due to save=True
            print("Accepting consultation...")
            consultation.accept(request.user)
            return Response(
                {
                    "status": consultation.status,
                    "consultation": ConsultationDetailSerializer(
                        consultation, context={"request": request}
                    ).data,
                }
            )
        except Exception as e:
            logger.error(f"Accept failed: {str(e)}", exc_info=True)
            return Response(
                {"error": "Acceptance failed"}, status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        try:
            consultation = self.get_object()
            reason = request.data.get("reason", "No reason provided")
            if consultation.status != "requested":
                return Response(
                    {"error": "Consultation must be in 'requested' state"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            with transaction.atomic():
                consultation.reject(request.user, reason)
                send_notification(consultation.patient.user.id, "Consultation rejected")
                return Response(
                    {
                        "status": "rejected",
                        "consultation": self.get_serializer(consultation).data,
                    }
                )
        except Consultation.DoesNotExist:
            logger.error(f"Consultation {pk} not found")
            return Response(
                {"error": "Consultation not found"}, status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Reject error: {str(e)}", exc_info=True)
            return Response(
                {"error": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        consultation = self.get_object()
        if consultation.status != "active":
            return Response(
                {"error": "Consultation must be active"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            consultation.refresh_from_db()
            consultation.complete()

            if consultation.status != "completed":
                return Response(
                    {"error": "Cannot complete consultation without chat history"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return Response(
                {
                    "status": consultation.status,
                    "consultation": self.get_serializer(consultation).data,
                }
            )
        except Exception as e:
            logger.error(f"Completion failed: {str(e)}", exc_info=True)
            return Response(
                {"error": "Completion failed - " + str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

import json
from django.conf import settings

with open('ml_models/diseases.json', 'r') as f:
    SYMPTOMS_DATA = json.load(f)

class SymptomListView(viewsets.ViewSet):
    """
    ViewSet to provide the list of available symptoms for selection
    """
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        try:
            # Format symptoms with IDs
            formatted_symptoms = [
                {'id': idx, 'name': symptom} 
                for idx, symptom in enumerate(SYMPTOMS_DATA)
            ]
            
            return Response({
                'count': len(SYMPTOMS_DATA),
                'results': formatted_symptoms
            })
        except Exception as e:
            logger.error(f"Failed to fetch symptoms list: {str(e)}")
            return Response(
                {'error': 'Failed to load symptoms list'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        

class PatientViewSet(viewsets.ModelViewSet):
    serializer_class = PatientSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id"
    lookup_url_kwarg = "pk"

    def get_queryset(self):
        # For staff users, return all patients
        if self.request.user.is_staff:
            return Patient.objects.all().order_by('user_id')
        # For regular users, return only their own patient profile
        return Patient.objects.filter(user=self.request.user).order_by('user_id')

    @action(detail=False, methods=['get'], permission_classes=[IsAdminUser])
    def all_patients(self, request):
        """
        Special endpoint only for admin users to get all patients
        """
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            patient = serializer.save()
            return Response(
                PatientSerializer(patient).data,
                status=status.HTTP_201_CREATED,
            )
        except ValidationError as e:
            logger.warning(f"Validation error: {str(e)}")
            return Response(
                {"error": "Validation error"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to create patient profile"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        
        # Only allow staff or the patient themselves to update
        if not (request.user.is_staff or instance.user == request.user):
            return Response(
                {"error": "You don't have permission to perform this action"},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        try:
            patient = serializer.save()
            return Response(PatientSerializer(patient).data)
        except ValidationError as e:
            logger.warning(f"Validation error: {str(e)}")
            return Response(
                {"error": "Validation error"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to update patient profile"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )