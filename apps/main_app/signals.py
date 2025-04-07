from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.accounts.models import User
from .models import Doctor, Patient
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def handle_user_profiles(sender, instance, created, **kwargs):
    """Create/update profiles based on user type"""
    try:
        if instance.user_type == "Doctor":
            if created or not hasattr(instance, "doctor_profile"):
                Doctor.objects.get_or_create(user=instance)
                logger.info(f"Created doctor profile for {instance.email}")

        if instance.user_type == "Patient":
            if created or not hasattr(instance, "patient_profile"):
                # Note: This will create empty profile - ensure registration flow collects required fields
                Patient.objects.get_or_create(user=instance)
                logger.info(f"Created patient profile for {instance.email}")

    except Exception as e:
        logger.error(f"Error creating profile for {instance.email}: {str(e)}")
