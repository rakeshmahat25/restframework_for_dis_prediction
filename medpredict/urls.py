from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter, SimpleRouter
from rest_framework_simplejwt.views import TokenRefreshView
from django.http import HttpResponse

# API
from apps.accounts.api import AuthViewSet, UserViewSet
from apps.main_app.api import (
    PredictionViewSet,
    DoctorViewSet,
    ConsultationViewSet,
    SymptomListView,
    DoctorConsultationViewSet,
)

from apps.chats.api import ChatViewSet, FeedbackViewSet

# router instance
router = DefaultRouter() if settings.DEBUG else SimpleRouter()

# Accounts App
router.register("auth", AuthViewSet, basename="auth")
router.register("users", UserViewSet, basename="users")

# Main App
router.register("predictions", PredictionViewSet, basename="predictions")
router.register("doctors", DoctorViewSet, basename="doctors")

# Separate registrations for patient and doctor consultations
router.register("consultations", ConsultationViewSet, basename="patient-consultations")
router.register(
    "doctor-consultations", DoctorConsultationViewSet, basename="doctor-consultations"
)

# Chats App
router.register("chats", ChatViewSet, basename="chats")
router.register("feedback", FeedbackViewSet, basename="feedback")
router.register("Symptoms", SymptomListView, basename="Symptoms")


def api_home_view(request):
    return HttpResponse(
        "Welcome to the MedPredict API. Explore the endpoints under /api/v1/."
    )


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(router.urls)),
    path("api/v1/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("", api_home_view, name="home"),
    path("api/v1/health/", lambda r: HttpResponse(status=200)),
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    path("api/v1/docs/", include("rest_framework_docs.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
