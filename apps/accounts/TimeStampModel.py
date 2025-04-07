# models.py

from django.db.models import Model, DateTimeField


class TimeStampModel(Model):
    """
    An abstract base class model that provides self-updating
    `created_at` and `updated_at` fields.
    """

    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)

    class Meta:
        abstract = True
