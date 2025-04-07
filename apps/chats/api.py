from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle, ScopedRateThrottle
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from .models import Chat, Feedback
from .serializers import ChatSerializer, FeedbackSerializer
from .permissions import IsConsultationParticipant
from .filters import ChatFilter, FeedbackFilter
from apps.main_app.models import Consultation
import logging
import traceback

logger = logging.getLogger(__name__)


class ChatPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


class ChatViewSet(viewsets.ModelViewSet):
    serializer_class = ChatSerializer
    permission_classes = [permissions.IsAuthenticated, IsConsultationParticipant]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = ChatFilter
    throttle_scope = "chats"
    throttle_classes = [ScopedRateThrottle]
    search_fields = ["message"]
    pagination_class = ChatPagination

    def get_queryset(self):
        user = self.request.user
        return Chat.objects.filter(consultation__participants=user).select_related(
            "sender", "consultation"
        )

    def create(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                # Atomic consultation retrieval with lock
                consultation_id = int(request.data.get("consultation"))
                consultation = get_object_or_404(
                    Consultation.objects.select_for_update(), id=consultation_id
                )

                # Immediate validation checks
                if consultation.status != "active":
                    logger.warning(f"Inactive consultation: {consultation_id}")
                    return Response(
                        {"error": "Consultation is not active"},
                        status=status.HTTP_403_FORBIDDEN,
                    )

                if not consultation.participants.filter(id=request.user.id).exists():
                    logger.error(f"Unauthorized user: {request.user.id}")
                    return Response(
                        {"error": "Not authorized for this consultation"},
                        status=status.HTTP_403_FORBIDDEN,
                    )

                # Proceed with chat creation
                logger.info(f"Creating chat for consultation: {consultation_id}")
                return super().create(request, *args, **kwargs)

        except (ValueError, TypeError) as e:
            logger.error(f"Invalid consultation ID: {str(e)}")
            return Response(
                {"error": "Invalid consultation ID format"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error(f"Chat creation failed: {traceback.format_exc()}")
            return Response(
                {"error": "Message processing failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None):
        try:
            chat = self.get_object()
            if not chat:
                return Response(
                    {"error": "Chat not found"}, status=status.HTTP_404_NOT_FOUND
                )
            self.check_object_permissions(request, chat)
            chat.status = "read"
            chat.save()
            return Response(
                {"status": "success", "message": "Message marked as read"},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {"error": f"Error marking as read: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(
        detail=False,
        methods=["post"],
        url_path="end-consultation/(?P<consultation_id>[^/.]+)",
    )
    def end_consultation(self, request, consultation_id=None):
        try:
            consultation = Consultation.objects.get(
                id=consultation_id, participants=request.user, status="active"
            )

            if not consultation.chats.exists():
                return Response(
                    {"error": "Cannot end consultation without chat history"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            consultation.complete()
            return Response(
                {
                    "status": "completed",
                    "message": "Consultation successfully ended",
                    "chat_count": consultation.chats.count(),
                }
            )

        except Consultation.DoesNotExist:
            return Response(
                {"error": "Invalid or unauthorized consultation"},
                status=status.HTTP_403_FORBIDDEN,
            )
        except Exception as e:
            logger.error(f"Consultation end error: {str(e)}")
            return Response(
                {"error": "Failed to end consultation"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FeedbackThrottle(UserRateThrottle):
    rate = "20/hour"


class FeedbackViewSet(viewsets.ModelViewSet):
    serializer_class = FeedbackSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = FeedbackFilter
    search_fields = ["feedback"]

    def get_queryset(self):
        return Feedback.objects.filter(sender=self.request.user)

    def perform_create(self, serializer):
        serializer.save(sender=self.request.user)

    def get_throttles(self):
        if self.action == "create":
            return [FeedbackThrottle()]
        return super().get_throttles()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(
            {"status": "success", "data": serializer.data},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, url_path="recent")
    def recent_feedback(self, request):
        recent = self.get_queryset().order_by("-created")[:5]
        serializer = self.get_serializer(recent, many=True)
        return Response({"count": len(recent), "results": serializer.data})
