from datetime import date
from django.utils import timezone
from rest_framework import serializers
from apps.accounts.models import User
from django.core.exceptions import ValidationError
from .utils.data_loader import ML_DATA
import datetime
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from .models import Patient, DoctorAvailability, Consultation, RatingReview, Doctor
from rest_framework import serializers
from django.contrib.auth import get_user_model # Use this to get the User model
from .models import Doctor

User = get_user_model()


class SymptomInputSerializer(serializers.Serializer):
    symptoms = serializers.ListField(
        child=serializers.CharField(max_length=100),
        min_length=1,
        max_length=20,
        help_text="List of symptoms",
    )

    def validate_symptoms(self, value):
        cleaned = [s.strip().lower() for s in value]
        valid_symptoms = {s.lower() for s in ML_DATA["symptoms"]}
        invalid = set(cleaned) - valid_symptoms
        if invalid:
            raise serializers.ValidationError(
                {
                    "invalid_symptoms": list(invalid),
                    "suggestion": "Check spelling or use symptom synonyms",
                }
            )
        return sorted(cleaned)



class DoctorSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source='user.id', read_only=True) # Assuming User PK is UUID
    email = serializers.EmailField(source='user.email', read_only=True)
    full_name = serializers.SerializerMethodField() # Keep this definition
    experience_years = serializers.SerializerMethodField()
    is_available = serializers.BooleanField(source='available', read_only=True)
    rating = serializers.IntegerField(read_only=True)

    class Meta:
        model = Doctor
        fields = [
            'id', 'full_name', 'email', 'specialization', 'experience_years',
            'qualification', 'gender', 'mobile_no', 'address', 'rating',
            'is_available', 'registration_no', 'year_of_registration',
            'state_medical_council', 'dob',
        ]
        read_only_fields = fields

    def get_full_name(self, obj):
        """
        Constructs the full name using available fields from the User model
        or the Doctor model's name field.
        """
        if obj.user:
            user = obj.user
            
            first = getattr(user, 'first_name', '')
            last = getattr(user, 'last_name', '')
            if first or last:
                return f"{first} {last}".strip()

            if obj.name:
                 return obj.name

            # --- Option 3: Fallback to User's username field ---
            if hasattr(user, 'username') and user.username:
                 return user.username
            return f"User {user.pk}"

        return "N/A" 

    def get_experience_years(self, obj):
        # ... (keep this method as before) ...
        if obj.year_of_registration:
            try:
                current_year = datetime.date.today().year
                experience = current_year - int(obj.year_of_registration)
                return max(0, experience)
            except (ValueError, TypeError):
                return None
        return None


class DoctorAvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = DoctorAvailability
        fields = ['id', 'start_time', 'end_time', 'is_booked']


class DoctorAvailabilityUpdateSerializer(serializers.Serializer):
    """
    Serializer for updating the doctor's availability status.
    """
    available = serializers.BooleanField(required=True)



class DoctorFeedbackSerializer(serializers.ModelSerializer):
    """
    Serializer for displaying Doctor Feedback.
    Includes patient information safely.
    """
    # Include the patient's name for context, but don't expose sensitive info like ID/email by default.
    # Use a SerializerMethodField for robust handling of different user models and potential null patients.
    patient_name = serializers.SerializerMethodField()
    # Format the created_at timestamp for better readability (optional)
    created_at_formatted = serializers.DateTimeField(source='created_at', format="%Y-%m-%d %H:%M", read_only=True)

    class Meta:
        model = RatingReview
        fields = [
            'id',
            'rating',
            'comment',
            'patient_name', # Include the calculated patient name
            'created_at', # Raw timestamp (good for sorting/filtering)
            'created_at_formatted', # User-friendly display format
        ]
        # Explicitly make fields read-only if this serializer is *only* for display
        read_only_fields = fields

    def get_patient_name(self, obj):
        """
        Safely retrieves the name of the patient who provided the feedback.
        Provides fallbacks for different user model fields or anonymous feedback.
        """
        # obj is the Feedback instance
        if obj.patient:
            user = obj.patient # The user linked via the 'patient' ForeignKey

            # 1. Try standard Django User method (if available)
            if hasattr(user, 'get_full_name') and user.get_full_name():
                return user.get_full_name()

            # 2. Fallback: Try combining first_name/last_name attributes
            first = getattr(user, 'first_name', '')
            last = getattr(user, 'last_name', '')
            if first or last:
                return f"{first} {last}".strip()

            # 3. Fallback: Use username (common fallback)
            if hasattr(user, 'username') and user.username:
                return user.username

            # 4. Fallback: If truly no name, use a generic identifier
            return f"User {user.pk}" # Or "Registered User"

        # Handle cases where patient is NULL (e.g., account deleted or anonymous allowed)
        return "Anonymous"



class PatientSerializer(serializers.ModelSerializer):

    class Meta:
        model = Patient
        fields = [
            'name',
            'age',
            'gender',
            'mobile_no',
            'address',
            'dob'
        ]
        extra_kwargs = {
            'dob': {'write_only': True},  # Hide in responses since we show age
            'address': {'required': False}  # Make address optional
        }

    def validate_name(self, value):
        """Ensure name contains only letters and spaces"""
        if not all(x.isalpha() or x.isspace() for x in value):
            raise serializers.ValidationError("Name can only contain letters and spaces")
        return value.strip()

    def to_representation(self, instance):
        """Custom representation to include gender display"""
        representation = super().to_representation(instance)
        representation['gender'] = instance.get_gender_display()
        return representation



class ConsultationCreateSerializer(serializers.ModelSerializer):
    doctor_id = serializers.CharField(write_only=True)
    disease_name = serializers.CharField()
    patient_id = serializers.CharField(source="patient.id", read_only=True)
    message = serializers.CharField()

    class Meta:
        model = Consultation
        fields = ["doctor_id","patient_id", "disease_name", "message", "consultation_date"]
        extra_kwargs = {"consultation_date": {"required": True}}

    def validate_doctor_id(self, value):
        try:
            # Changed from id to user_id
            doctor = Doctor.objects.get(user_id=value, available=True)
            if not doctor.user:
                raise serializers.ValidationError("Doctor account not properly configured.")
            return doctor
        except Doctor.DoesNotExist:
            raise serializers.ValidationError("No available doctor found with this ID.")

    def validate(self, attrs):
        # Run base validation first
        attrs = super().validate(attrs)

        # Get doctor instance from validate_doctor_id
        doctor = attrs.pop("doctor_id")  

        # Add doctor to validated data
        attrs["doctor"] = doctor

        # Check for existing consultation
        if Consultation.objects.filter(
            patient=self.context["request"].user.patient_profile,
            doctor=doctor,
            consultation_date=attrs["consultation_date"],
        ).exists():
            raise serializers.ValidationError(
                {
                    "non_field_errors": [
                        "You already have a consultation with this doctor on this date"
                    ]
                }
            )

        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        try:
            patient = user.patient_profile
        except Patient.DoesNotExist:
            raise serializers.ValidationError(
                {
                    "patient": "Patient profile not found. Complete your profile to create a consultation."
                }
            )

        doctor = validated_data["doctor"]
        validated_data.update(
            {
                "patient": patient,
                "consult_doctor": doctor.specialization,
            }
        )

        consultation = super().create(validated_data)
        # Add both participants
        consultation.participants.add(user, consultation.doctor.user)
        return consultation


class ConsultationDetailSerializer(serializers.ModelSerializer):
    patient = serializers.PrimaryKeyRelatedField(queryset=Patient.objects.all())
    doctor = serializers.PrimaryKeyRelatedField(queryset=Doctor.objects.all())

    # Read-only fields for display
    patient_id = serializers.CharField(source="patient.id", read_only=True)
    doctor_id = serializers.CharField(source="doctor.id", read_only=True)
    specialist = serializers.CharField(source="get_consult_doctor_display", read_only=True)
    patient_age = serializers.SerializerMethodField(source="get_patient_age", read_only=True)
    patient_gender = serializers.CharField(source="patient.gender", read_only=True)

    class Meta:
        model = Consultation
        fields = [
            "id",
            "status",
            "patient", 
            "patient_id",
            "doctor",  
            "doctor_id",  
            "disease_name",
            "specialist",
            "message",
            "consultation_date",
            "created_at",
            "rejection_reason",
            "patient_age",
            "patient_gender",
        ]
        read_only_fields = [
             "created_at",
        ]

    def get_patient_age(self, obj):
        return obj.patient.age


class RatingSerializer(serializers.ModelSerializer):
    class Meta:
        model = RatingReview
        fields = ["rating", "review"]
        extra_kwargs = {"rating": {"min_value": 1, "max_value": 5}}

    def validate(self, data):
        consultation = self.context["consultation"]
        if not consultation.is_ratable():
            raise serializers.ValidationError(
                "Can only rate completed consultations with chat history"
            )
        if RatingReview.objects.filter(
            patient=consultation.patient, doctor=consultation.doctor
        ).exists():
            raise serializers.ValidationError(
                "You have already rated this consultation"
            )
        return data
