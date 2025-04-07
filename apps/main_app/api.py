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
from apps.main_app.models import DiseaseInfo, Consultation, Doctor, RatingReview, Patient
from .serializers import (
    SymptomInputSerializer,
    DoctorSerializer,
    PatientSerializer,
    ConsultationCreateSerializer,
    ConsultationDetailSerializer,
    RatingSerializer,
)
from apps.accounts.permissions import IsPatient, IsDoctor
from .utils.data_loader import ML_DATA, MODEL
import logging

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


class PredictionViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsPatient]
    throttle_scope = "predictions"

    @action(detail=False, methods=["post"])
    def predict_disease(self, request):
        serializer = SymptomInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        symptoms = sorted(serializer.validated_data["symptoms"])

        symptoms_set = set(symptoms)
        concatenated = "".join(symptoms)
        cache_key = f"prediction_{hashlib.md5(concatenated.encode()).hexdigest()}"

        if cached := cache.get(cache_key):
            return Response(cached)

        vector = [1 if s in symptoms_set else 0 for s in ML_DATA["symptoms"]]

        try:
            X_input = pd.DataFrame([vector], columns=ML_DATA["symptoms"])
            disease_idx = MODEL.predict(X_input)[0]
            disease_name = ML_DATA["label_encoder"].inverse_transform([disease_idx])[0]
            confidence = round(MODEL.predict_proba(X_input).max() * 100, 2)
        except IndexError as e:
            logger.error(f"Invalid disease index {disease_idx}: {str(e)}")
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

        recommended_specialization = ML_DATA["disease_mapping"].get(
            disease_name, "General Physician"
        )

        try:
            with transaction.atomic():
                disease_info = DiseaseInfo.objects.create(
                    patient=request.user.patient_profile,
                    symptoms=symptoms,
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
                cache.set(cache_key, result, timeout=3600)
        except Exception as e:
            logger.error(f"Database error: {str(e)}")
            return Response(
                {"error": "Unable to save prediction result"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(result)


class DoctorViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DoctorSerializer

    def get_queryset(self):
        return (
            Doctor.objects.filter(available=True)
            .annotate(avg_rating=Avg("ratings__rating"))
            .select_related("user")
            .prefetch_related("ratings")
            .order_by("-year_of_registration")
        )


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