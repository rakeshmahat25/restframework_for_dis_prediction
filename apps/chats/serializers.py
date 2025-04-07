from rest_framework import serializers
from .models import Chat, Feedback
from apps.main_app.models import Consultation, Doctor


class ChatSerializer(serializers.ModelSerializer):
    consultation = serializers.PrimaryKeyRelatedField(
        queryset=Consultation.objects.all()
    ) 
    sender = serializers.StringRelatedField(read_only=True)
    timestamp = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Chat
        fields = [
            "id",
            "created",
            "consultation",
            "sender",
            "message",
            "status",
            "timestamp",
        ]
        read_only_fields = [
            "id",
            "created",
            "sender",
            "status",
            "timestamp",
        ]

    def validate_consultation(self, value):
        request = self.context.get("request")
        if not request or not request.user:
            raise serializers.ValidationError("Authentication required.")

        # Ensure the user is a participant in the consultation
        if not value.participants.filter(id=request.user.id).exists():
            raise serializers.ValidationError("Not a participant in this consultation.")

        return value

    def create(self, validated_data):
        validated_data["sender"] = self.context["request"].user
        return super().create(validated_data)


class FeedbackSerializer(serializers.ModelSerializer):
    sender = serializers.StringRelatedField(read_only=True)
    doctor = serializers.PrimaryKeyRelatedField(queryset=Doctor.objects.all())

    class Meta:
        model = Feedback
        fields = ["id", "created", "sender", "doctor", "feedback"]
        read_only_fields = ["id", "created", "sender"]

    def validate_feedback(self, value):
        if len(value) < 10:
            raise serializers.ValidationError(
                "Feedback must be at least 10 characters long."
            )
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        if not request or not request.user:
            raise serializers.ValidationError("Authentication required.")

        # Ensure the user is a patient
        if request.user.user_type != "Patient":
            raise serializers.ValidationError("Only patients can submit feedback.")

        # Check for completed consultation with the doctor
        has_completed = Consultation.objects.filter(
            patient=request.user.patient_profile,
            doctor=attrs.get("doctor"),
            status="completed",
        ).exists()

        if not has_completed:
            raise serializers.ValidationError(
                "No completed consultation found with this doctor."
            )

        return attrs

    def create(self, validated_data):
        validated_data["sender"] = self.context["request"].user
        return super().create(validated_data)
