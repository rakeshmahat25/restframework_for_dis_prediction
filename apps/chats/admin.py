from django.contrib import admin
from .models import Chat, Feedback


@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    list_display = ["id", "created", "consultation", "sender", "message"]
    search_fields = ["message", "sender__email"]
    list_filter = ["created"]
    # ordering = ["-created"]


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ["id", "created", "sender", "feedback"]
    search_fields = ["feedback", "sender__email"]
    list_filter = ["created"]
    # ordering = ["-created"]
