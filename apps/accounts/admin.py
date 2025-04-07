from django.contrib import admin
from .models import User, OTP


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "email",
        "username",
        "full_name",
        "user_type",
        "is_active",
    ]
    search_fields = ["email", "username"]
    list_filter = ["user_type", "is_active"]
    # ordering = ["-date_joined"]


@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    list_display = ["otp", "otp_type", "user", "is_used", "created_at"]
    search_fields = ["user__email", "otp"]
    list_filter = ["otp_type", "is_used"]
    # ordering = ["-created_at"]
