from rest_framework.permissions import BasePermission


class IsPatient(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.user_type == "Patient"
            and hasattr(request.user, "patient_profile")
        )


class IsDoctor(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == "Doctor"


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == "Admin"


class IsOTPVerified(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.otp_verified
