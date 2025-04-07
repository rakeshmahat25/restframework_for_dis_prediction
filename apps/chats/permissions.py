from rest_framework import permissions
from apps.main_app.models import Consultation


class IsConsultationParticipant(permissions.BasePermission):
    def has_permission(self, request, view):
        if view.action == "end_consultation":
            consultation_id = view.kwargs.get("consultation_id")
            return Consultation.objects.filter(
                id=consultation_id,
                participants__id=request.user.id,  # Proper M2M lookup
                status="active",
            ).exists()
        return True

    def has_object_permission(self, request, view, obj):
        # For Chat object permissions
        return obj.consultation.participants.filter(id=request.user.id).exists()
