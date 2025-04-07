from datetime import date
from django.utils import timezone
from rest_framework import serializers
from apps.accounts.models import User
from .models import DiseaseInfo, Consultation, Doctor, RatingReview, Patient
from .utils.data_loader import ML_DATA



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
    id = serializers.UUIDField(source="user_id")
    is_available = serializers.BooleanField(source="available")
    years_experience = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    specialization = serializers.CharField(source="get_specialization_display")

    class Meta:
        model = Doctor
        fields = [
            "id",
            "name",
            "specialization",
            "rating",
            "year_of_registration",
            "years_experience",
            "is_available",
            "qualification",
        ]

    def get_years_experience(self, obj):
        return date.today().year - obj.year_of_registration

    def get_rating(self, obj):
        avg_rating = getattr(obj, "avg_rating", None)
        return round(avg_rating, 1) if avg_rating is not None else 0.0


from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from .models import Patient


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
    doctor_name = serializers.CharField(write_only=True)
    disease_name = serializers.CharField()

    class Meta:
        model = Consultation
        fields = ["doctor_name", "disease_name", "message", "consultation_date"]
        extra_kwargs = {"consultation_date": {"required": True}}

    def validate_doctor_name(self, value):
        # Case-insensitive lookup and handle whitespace
        doctor_name = value.strip()
        doctors = Doctor.objects.filter(name__iexact=doctor_name, available=True)
        if not doctors.exists():
            raise serializers.ValidationError(
                "No available doctor found with this name."
            )
        if doctors.count() > 1:
            raise serializers.ValidationError(
                "Multiple doctors with this name. Please contact support."
            )
        doctor = doctors.first()
        if not doctor.user:
            raise serializers.ValidationError("Doctor account not properly configured.")
        return doctor

    def validate(self, attrs):
        # Run base validation first
        attrs = super().validate(attrs)

        # Extract doctor instance from doctor_name field
        doctor = attrs.pop("doctor_name")  

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
    patient_name = serializers.CharField(source="patient.name", read_only=True)
    doctor_name = serializers.CharField(source="doctor.name", read_only=True)
    specialist = serializers.CharField(source="get_consult_doctor_display", read_only=True)
    patient_age = serializers.SerializerMethodField()
    patient_gender = serializers.CharField(source="patient.gender", read_only=True)

    class Meta:
        model = Consultation
        fields = [
            "id",
            "status",
            "patient", 
            "doctor",  
            "patient_name", 
            "doctor_name",  
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
