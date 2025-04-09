from django.contrib import admin
from .models import Patient, Doctor, DiseaseInfo, Consultation, RatingReview, DoctorAvailability


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ["user", "name", "dob", "gender", "age", "mobile_no", "address"]
    search_fields = ["user__email", "name"]
    list_filter = ["gender"]
    ordering = ["name"]

@admin.register(DoctorAvailability)
class DoctorAvailabilityAdmin(admin.ModelAdmin):
    list_display = ('doctor', 'start_time', 'end_time', 'is_booked')
    list_filter = ('doctor', 'is_booked')
    search_fields = ('doctor__name',)


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "name",
        "specialization",
        "registration_no",
        "qualification",
        "rating",
    ]
    search_fields = ["user__email", "name", "specialization"]
    list_filter = ["specialization", "rating"]
    ordering = ["name"]


@admin.register(DiseaseInfo)
class DiseaseInfoAdmin(admin.ModelAdmin):
    list_display = [
        "patient",
        "disease_name",
        "no_of_symptoms",
        "confidence",
        "consult_doctor",
    ]
    search_fields = ["patient__user__email", "disease_name"]
    list_filter = ["confidence"]
    ordering = ["-confidence"]


@admin.register(Consultation)
class ConsultationAdmin(admin.ModelAdmin):
    list_display = ["patient", "doctor", "consultation_date", "status"]
    search_fields = ["patient__user__email", "doctor__user__email"]
    list_filter = ["status"]
    ordering = ["-consultation_date"]


@admin.register(RatingReview)
class RatingReviewAdmin(admin.ModelAdmin):
    list_display = ["patient", "doctor", "rating", "review", "average_rating"]
    search_fields = ["patient__user__email", "doctor__user__email"]
    list_filter = ["rating"]
    ordering = ["-rating"]
