import random
import uuid
from django.conf import settings
from django.contrib.auth.models import (
    AbstractBaseUser,
    PermissionsMixin,
    Group,
    Permission,
)
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

# from django.dispatch import receiver
from .TimeStampModel import TimeStampModel
from .managers import CustomUserManager



# Gender Choices
GENDER_CHOICES = [("Male", "Male"), ("Female", "Female"), ("Other", "Other")]

# OTP Types
OTP_TYPE_CHOICES = [
    ("Registration", "Registration"),
    ("Password Reset", "Password Reset"),
]

# User Types
USER_TYPE_CHOICES = [
    ("Patient", "Patient"),
    ("Doctor", "Doctor"),
    ("Admin", "Admin"),
]


# User Model
class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(_("email address"), unique=True)
    username = models.CharField(max_length=100, unique=True)
    full_name = models.CharField(max_length=255, blank=True, null=True)
    user_type = models.CharField(
        max_length=32, choices=USER_TYPE_CHOICES, default="Patient"
    )
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    otp_verified = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    last_login = models.DateTimeField(blank=True, null=True)
    login_count = models.BigIntegerField(default=0)

    # Add unique related_name for groups and user_permissions
    groups = models.ManyToManyField(
        Group,
        verbose_name=_("groups"),
        blank=True,
        help_text=_(
            "The groups this user belongs to. A user will get all permissions "
            "granted to each of their groups."
        ),
        related_name="custom_user_groups",  # Unique related_name
        related_query_name="custom_user",
    )
    user_permissions = models.ManyToManyField(
        Permission,
        verbose_name=_("user permissions"),
        blank=True,
        help_text=_("Specific permissions for this user."),
        related_name="custom_user_permissions",  # Unique related_name
        related_query_name="custom_user",
    )

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    objects = CustomUserManager()

    def get_login_response(self):
        res = {
            "id": self.id,
            "otp_verified": self.otp_verified,
            "email": self.email,
            "role":self.user_type,
            "name":self.username,
            "fullName":self.full_name

        }
        return res

    def first_login(self):
        if self.login_count == 1:
            return True
        return False

    def __str__(self):
        return self.email


# OTP Model
class OTP(TimeStampModel):
    otp = models.CharField(max_length=settings.OTP_LENGTH)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="otps")
    otp_type = models.CharField(max_length=20, choices=OTP_TYPE_CHOICES)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_expired(self):
        if (timezone.now() - self.created_at).seconds > settings.OTP_VALID_DURATION:
            return True
        return False

    @classmethod
    def create(cls, user_id: uuid.UUID, type: str):
        otp_length = settings.OTP_LENGTH
        start = int("1" + "0" * (otp_length - 1))
        end = int("9" * otp_length)

        if settings.DEBUG:
            code = int("1" * otp_length)  # Debug OTP
        else:
            code = random.randint(start, end)  # Random OTP

        # Convert code to string before saving
        otp = cls.objects.create(otp=str(code), user_id=user_id, otp_type=type)
        return otp

    class Meta:
        ordering = ["-created_at"]



