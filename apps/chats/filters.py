import django_filters
from .models import Chat, Feedback


class ChatFilter(django_filters.FilterSet):
    created = django_filters.DateTimeFromToRangeFilter()
    sender = django_filters.CharFilter(
        field_name="sender__email", lookup_expr="icontains"
    )
    status = django_filters.ChoiceFilter(
        choices=[
            ("sent", "Sent"),
            ("delivered", "Delivered"),
            ("read", "Read"),
        ]
    )
    consultation = django_filters.UUIDFilter(field_name="consultation__id")

    class Meta:
        model = Chat
        fields = ["consultation", "sender", "created", "status"]


class FeedbackFilter(django_filters.FilterSet):
    created = django_filters.DateTimeFromToRangeFilter()

    class Meta:
        model = Feedback
        fields = ["created"]
