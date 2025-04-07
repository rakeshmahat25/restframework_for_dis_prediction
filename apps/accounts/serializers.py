from rest_framework import serializers
from rest_framework.exceptions import ValidationError, AuthenticationFailed
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth import authenticate
from django.utils import timezone
from django.conf import settings
from .models import User, OTP
from apps.main_app.models import Patient, Doctor
from adapters.email.django_mail import DjangoMail


# Login Serializer
class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")
        user = authenticate(email=email, password=password)

        if not user:
            raise AuthenticationFailed("Invalid email or password.")

        if not user.is_active:
            raise AuthenticationFailed("Account is not active.")

        attrs["user"] = user
        return attrs


# Password Validation Mixin
class PasswordValidationMixin:
    def validate_password(self, password):
        validate_password(password)  # Django's built-in password validation
        return password


# Nested Serializers for Different User Types
class PatientSignupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = ["name", "dob", "address", "mobile_no", "gender"]

    def validate_mobile_no(self, value):
        if not value.isdigit():
            raise ValidationError("Mobile number must contain only digits.")
        return value


class DoctorSignupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Doctor
        fields = [
            "name",
            "dob",
            "address",
            "mobile_no",
            "gender",
            "registration_no",
            "year_of_registration",
            "qualification",
            "specialization",
            "state_medical_council",
        ]


class AdminSignupSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["email", "username", "full_name"]


# Signup Serializer
class SignupSerializer(PasswordValidationMixin, serializers.Serializer):
    USER_TYPE_SERIALIZERS = {
        "Patient": PatientSignupSerializer,
        "Doctor": DoctorSignupSerializer,
        "Admin": AdminSignupSerializer,
    }

    USER_TYPE_CHOICES = list(USER_TYPE_SERIALIZERS.keys())

    user_type = serializers.ChoiceField(choices=USER_TYPE_CHOICES)
    data = serializers.JSONField()
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        # Validate passwords match
        if attrs["password"] != attrs.pop("confirm_password", None):
            raise ValidationError("Passwords do not match.")
        self.validate_password(attrs["password"])

        # Validate email and username
        email = attrs["data"].get("email")
        username = attrs["data"].get("username")
        if not email or not username:
            raise ValidationError("Email and username are required.")

        if User.objects.filter(email=email).exists():
            raise ValidationError("Email already registered.")
        if User.objects.filter(username=username).exists():
            raise ValidationError("Username already taken.")

        # Validate nested data for the specified user type
        user_type = attrs["user_type"]
        data_serializer_class = self.USER_TYPE_SERIALIZERS.get(user_type)
        if not data_serializer_class:
            raise ValidationError("Invalid user type.")

        data_serializer = data_serializer_class(data=attrs["data"])
        data_serializer.is_valid(raise_exception=True)

        # Preserve email and username in the validated data
        validated_data = data_serializer.validated_data
        validated_data["email"] = email
        validated_data["username"] = username

        attrs["data"] = validated_data
        return attrs

    def create(self, validated_data):
        user_type = validated_data["user_type"]
        data = validated_data.pop("data")
        password = validated_data.pop("password")

        # Create User instance
        user = User.objects.create(
            email=data["email"],
            username=data["username"],
            user_type=user_type,
            full_name=data.get("full_name", ""),  # For Admin
        )
        user.set_password(password)
        user.save()

        # Create profile only for Patient/Doctor
        if user_type in ["Patient", "Doctor"]:
            profile_data = {
                "name": data.get("name"),
                "dob": data.get("dob"),
                "address": data.get("address"),
                "mobile_no": data.get("mobile_no"),
                "gender": data.get("gender"),
            }
            if user_type == "Doctor":
                profile_data.update(
                    {
                        "registration_no": data.get("registration_no"),
                        "year_of_registration": data.get("year_of_registration"),
                        "qualification": data.get("qualification"),
                        "specialization": data.get("specialization"),
                        "state_medical_council": data.get("state_medical_council"),
                    }
                )
            self.USER_TYPE_SERIALIZERS[user_type].Meta.model.objects.create(
                user=user, **profile_data
            )

        # Generate OTP
        otp = OTP.create(user.id, "Registration")
        print(f"OTP generated: {otp.otp} for user: {user.email}")  # Debugging

        # Send OTP email
        if not settings.DEBUG:
            DjangoMail().send(
                {
                    "subject": "Registration OTP",
                    "message": f"Your OTP is {otp.otp}. Please verify your registration.",
                    "to": [user.email],
                }
            )

        return user


# OTP Verification Serializer
class OTPVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField()

    def validate(self, attrs):
        email = attrs["email"]
        otp = attrs["otp"]

        user = User.objects.filter(email=email).first()
        if not user:
            raise ValidationError("User with this email does not exist.")

        otp_instance = OTP.objects.filter(user=user, otp=otp, is_used=False).first()
        if not otp_instance:
            raise ValidationError("Invalid or expired OTP.")

        if otp_instance.is_expired or otp_instance.is_used:
            raise ValidationError("Invalid or expired OTP.")

        attrs["user"] = user
        attrs["otp_instance"] = otp_instance
        return attrs


# User List Serializer
class UserListSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email"]


# User Update Serializer to update both User and its associated profile
class UserUpdateSerializer(serializers.ModelSerializer):
    # for updating the associated profile
    name = serializers.CharField(required=False)
    dob = serializers.DateField(required=False)
    address = serializers.CharField(required=False)
    mobile_no = serializers.CharField(required=False)
    gender = serializers.CharField(required=False)
    # Doctor-specific fields
    registration_no = serializers.CharField(required=False)
    year_of_registration = serializers.IntegerField(required=False)
    qualification = serializers.CharField(required=False)
    specialization = serializers.CharField(required=False)
    state_medical_council = serializers.CharField(required=False)

    class Meta:
        model = User
        fields = [
            "full_name",
            "email",
            "username",
            "name",
            "dob",
            "address",
            "mobile_no",
            "gender",
            # Doctor-specific fields
            "registration_no",
            "year_of_registration",
            "qualification",
            "specialization",
            "state_medical_council",
        ]

    def update(self, instance, validated_data):
        # Update User model fields
        instance.full_name = validated_data.get("full_name", instance.full_name)
        instance.email = validated_data.get("email", instance.email)
        instance.username = validated_data.get("username", instance.username)
        instance.save()

        # Update the associated profile if it exists
        if instance.user_type == "Patient" and hasattr(instance, "patient_profile"):
            patient_profile = instance.patient_profile
            patient_profile.name = validated_data.get("name", patient_profile.name)
            patient_profile.dob = validated_data.get("dob", patient_profile.dob)
            patient_profile.address = validated_data.get(
                "address", patient_profile.address
            )
            patient_profile.mobile_no = validated_data.get(
                "mobile_no", patient_profile.mobile_no
            )
            patient_profile.gender = validated_data.get(
                "gender", patient_profile.gender
            )
            patient_profile.save()

        elif instance.user_type == "Doctor" and hasattr(instance, "doctor_profile"):
            doctor_profile = instance.doctor_profile
            doctor_profile.name = validated_data.get("name", doctor_profile.name)
            doctor_profile.dob = validated_data.get("dob", doctor_profile.dob)
            doctor_profile.address = validated_data.get(
                "address", doctor_profile.address
            )
            doctor_profile.mobile_no = validated_data.get(
                "mobile_no", doctor_profile.mobile_no
            )
            doctor_profile.gender = validated_data.get("gender", doctor_profile.gender)
            doctor_profile.registration_no = validated_data.get(
                "registration_no", doctor_profile.registration_no
            )
            doctor_profile.year_of_registration = validated_data.get(
                "year_of_registration", doctor_profile.year_of_registration
            )
            doctor_profile.qualification = validated_data.get(
                "qualification", doctor_profile.qualification
            )
            doctor_profile.specialization = validated_data.get(
                "specialization", doctor_profile.specialization
            )
            doctor_profile.state_medical_council = validated_data.get(
                "state_medical_council", doctor_profile.state_medical_council
            )
            doctor_profile.save()

        return instance


# User Profile Serializer
class UserProfileSerializer(serializers.ModelSerializer):
    age = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    dob = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()
    mobile_no = serializers.SerializerMethodField()
    gender = serializers.SerializerMethodField()
    registration_no = serializers.SerializerMethodField()
    specialization = serializers.SerializerMethodField()

    def get_age(self, obj):
        try:
            if obj.user_type == "Patient":
                patient = obj.patient_profile
                if patient.dob:
                    return timezone.now().year - patient.dob.year
            elif obj.user_type == "Doctor":
                doctor = obj.doctor_profile
                if doctor.dob:
                    return timezone.now().year - doctor.dob.year
        except (Patient.DoesNotExist, Doctor.DoesNotExist):
            pass
        return None

    def get_name(self, obj):
        if obj.user_type == "Admin":
            return obj.full_name
        try:
            if obj.user_type == "Patient":
                return obj.patient_profile.name
            elif obj.user_type == "Doctor":
                return obj.doctor_profile.name
        except (Patient.DoesNotExist, Doctor.DoesNotExist):
            return None
        return None

    def get_dob(self, obj):
        try:
            if obj.user_type == "Patient":
                return obj.patient_profile.dob
            elif obj.user_type == "Doctor":
                return obj.doctor_profile.dob
        except (Patient.DoesNotExist, Doctor.DoesNotExist):
            return None

    def get_address(self, obj):
        try:
            if obj.user_type == "Patient":
                return obj.patient_profile.address
            elif obj.user_type == "Doctor":
                return obj.doctor_profile.address
        except (Patient.DoesNotExist, Doctor.DoesNotExist):
            return None

    def get_mobile_no(self, obj):
        try:
            if obj.user_type == "Patient":
                return obj.patient_profile.mobile_no
            elif obj.user_type == "Doctor":
                return obj.doctor_profile.mobile_no
        except (Patient.DoesNotExist, Doctor.DoesNotExist):
            return None

    def get_gender(self, obj):
        try:
            if obj.user_type == "Patient":
                return obj.patient_profile.gender
            elif obj.user_type == "Doctor":
                return obj.doctor_profile.gender
        except (Patient.DoesNotExist, Doctor.DoesNotExist):
            return None

    def get_registration_no(self, obj):
        if obj.user_type == "Doctor" and hasattr(obj, "doctor_profile"):
            return obj.doctor_profile.registration_no
        return None

    def get_specialization(self, obj):
        if obj.user_type == "Doctor" and hasattr(obj, "doctor_profile"):
            return obj.doctor_profile.specialization
        return None

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "full_name",
            "user_type",
            "date_joined",
            "age",
            "name",
            "dob",
            "address",
            "mobile_no",
            "gender",
            "registration_no",
            "specialization",
        ]
