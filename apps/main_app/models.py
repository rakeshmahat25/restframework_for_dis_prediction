from django.db import models, transaction
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.contrib.postgres.fields import ArrayField
from apps.accounts.models import User, GENDER_CHOICES
from datetime import date
# from viewflow.fsm import FSMField, transition  # Remove the import
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

SPECIALIZATION_CHOICES = [
    ("Allergist", "Allergist"),
    ("Cardiologist", "Cardiologist"),
    ("Dentist", "Dentist"),
    ("Dermatologist", "Dermatologist"),
    ("Endocrinologist", "Endocrinologist"),
    ("ENT Specialist", "ENT Specialist"),
    ("Gastroenterologist", "Gastroenterologist"),
    ("General Physician", "General Physician"),
    ("Hepatologist", "Hepatologist"),
    ("Infectious Disease Specialist", "Infectious Disease Specialist"),
    ("Nephrologist", "Nephrologist"),
    ("Neurologist", "Neurologist"),
    ("Orthopedist", "Orthopedist"),
    ("Psychiatrist", "Psychiatrist"),
    ("Pulmonologist", "Pulmonologist"),
    ("Rheumatologist", "Rheumatologist"),
    ("Urologist", "Urologist"),
]


def validate_user_is_doctor(user):
    if user.user_type != "Doctor":
        raise ValidationError("User must be a doctor to create this profile")


class Patient(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, primary_key=True, related_name="patient_profile"
    )
    name = models.CharField(max_length=50)
    dob = models.DateField()
    address = models.CharField(max_length=100)
    mobile_no = models.CharField(max_length=15)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)

    @property
    def age(self):
        today = date.today()
        db = self.dob
        age = today.year - db.year
        if today.month < db.month or (today.month == db.month and today.day < db.day):
            age -= 1
        return age

    def __str__(self):
        return f"Patient {self.name}"


class Doctor(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="doctor_profile",
        validators=[validate_user_is_doctor],
    )
    name = models.CharField(max_length=50)
    dob = models.DateField()
    address = models.CharField(max_length=100)
    mobile_no = models.CharField(max_length=15)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    registration_no = models.CharField(max_length=20)
    available = models.BooleanField(default=True)
    year_of_registration = models.IntegerField()
    qualification = models.CharField(max_length=20)
    state_medical_council = models.CharField(max_length=30)
    specialization = models.CharField(max_length=30, choices=SPECIALIZATION_CHOICES)
    rating = models.IntegerField(default=0)

    def __str__(self):
        return f"Doctor {self.name}"

class DoctorAvailability(models.Model):
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='availabilities')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    is_booked = models.BooleanField(default=False)


    def __str__(self):
        return f"{self.doctor.name} - {self.start_time.strftime('%Y-%m-%d %H:%M')}"

class DiseaseInfo(models.Model):
    patient = models.ForeignKey(
        Patient, null=True, on_delete=models.SET_NULL, related_name="diseases"
    )
    disease_name = models.CharField(max_length=200)
    no_of_symptoms = models.IntegerField()
    symptoms = ArrayField(models.CharField(max_length=200))
    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    consult_doctor = models.CharField(max_length=200, choices=SPECIALIZATION_CHOICES)

    def get_recommended_doctors(self):
        return Doctor.objects.filter(
            specialization=self.consult_doctor, available=True
        ).select_related("user")

    def __str__(self):
        return f"Disease {self.disease_name} for {self.patient.name}"


class Consultation(models.Model):
    STATUS_CHOICES = [
        ("requested", "Requested"),
        ("active", "Active"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="requested",  # Set a default value
    )
    rejection_reason = models.TextField(blank=True, null=True)
    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="consultations"
    )
    doctor = models.ForeignKey(
        Doctor, on_delete=models.CASCADE, related_name="consultations"
    )
    disease_name = models.CharField(max_length=200, default="Migraine")
    consult_doctor = models.CharField(
        max_length=200, choices=SPECIALIZATION_CHOICES, default="General Physician"
    )
    message = models.TextField(default="Feel free to msg doctor")
    consultation_date = models.DateField(default=date.today)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    participants = models.ManyToManyField(
        User, related_name="consultations_joined", blank=True
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    def can_chat(self):
        return self.status == "active"

    def is_ratable(self):
        return self.status == "completed" and self.chats.exists()

    
    @transaction.atomic
    def accept(self, user):
        
        print(self.status) #Value of state before change.
        if self.status != "requested":
            raise ValidationError("Consultation is not in the 'requested' state.")

        self.status = "active"
        print(self.status) #Value of change
        # Save state transition first
        self.save()

        # Add both doctor and patient to participants
        print(user.id) #Correct Doctor Value
        print(self.patient.user.id) #Correct Patient value
        self.participants.add(user, self.patient.user)
        #Add the doctor profile, it only adds the user now
        self.participants.add(user.doctor_profile.user)

        logger.info(f"Consultation {self.id} accepted by {user}")
        transaction.on_commit(
            lambda: self.notify_participants(f"Consultation accepted by {user}")
        )

    @transaction.atomic
    def reject(self, user, reason):
        if self.status != "requested":
            raise ValidationError("Consultation is not in the 'requested' state.")
        self.rejection_reason = reason
        self.status = "cancelled"
        self.save()  # Save both status and reason
        self.log_rejection(reason=reason, rejected_by=user)
        logger.info(f"Consultation {self.id} rejected by {user}")
        transaction.on_commit(
            lambda: self.notify_participants(f"Consultation cancelled by {user}")
        )

    @transaction.atomic
    def complete(self):
        if self.status != "active" or not self.chats.exists():
           raise ValidationError("Consultation is not in the 'active' state or has no chats.")
        self.status = "completed"
        self.archived_at = timezone.now()
        self.save()
        logger.info(f"Consultation {self.id} completed")
        transaction.on_commit(
            lambda: self.notify_participants("Consultation completed")
        )

    def notify_participants(self, message):
        try:
            channel_layer = get_channel_layer()
            for participant in self.participants.all():
                async_to_sync(channel_layer.group_send)(
                    f"user_{participant.id}",
                    {"type": "consultation_notification", "message": message},
                )
            logger.info(f"Notified all participants: {message}")
        except Exception as e:
            logger.error(f"Notification failed: {str(e)}")

    def log_rejection(self, reason, rejected_by):
        try:
            logger.info(
                f"Consultation {self.id} rejected by {rejected_by}. Reason: {reason}"
            )
        except Exception as e:
            logger.error(f"Error logging rejection for consultation {self.id}: {e}")
            raise

    def archive(self):
        try:
            self.archived_at = timezone.now()
            self.save(update_fields=["archived_at"])
            logger.info(f"Consultation {self.id} archived at {self.archived_at}")
        except Exception as e:
            logger.error(f"Error archiving consultation {self.id}: {e}")
            raise

    def clean(self):
        if not hasattr(self.patient, "user") or not hasattr(self.doctor, "user"):
            raise ValidationError("Missing user association for patient or doctor")

    def is_participant(self, user):
        return self.participants.filter(id=user.id).exists()

    def __str__(self):
        return (
            f"Consultation {self.id} between {self.patient.name} and {self.doctor.name}"
        )

    class Meta:
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["doctor", "patient"]),
            models.Index(fields=["consultation_date"]),
            models.Index(fields=["archived_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["patient", "doctor", "consultation_date"],
                name="unique_consultation",
                deferrable=models.Deferrable.DEFERRED,
            )
        ]


class RatingReview(models.Model):
    patient = models.ForeignKey(
        Patient, null=True, on_delete=models.SET_NULL, related_name="ratings"
    )
    doctor = models.ForeignKey(
        Doctor, null=True, on_delete=models.SET_NULL, related_name="ratings"
    )
    rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    review = models.TextField(blank=True)

    @property
    def average_rating(self):
        ratings = RatingReview.objects.filter(doctor=self.doctor)
        if ratings.exists():
            return sum(r.rating for r in ratings) / len(ratings)
        return 0

    def __str__(self):
        return f"Rating {self.rating} by {self.patient.name} for {self.doctor.name}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["patient", "doctor"], name="one_rating_per_doctor"
            )
        ]



    