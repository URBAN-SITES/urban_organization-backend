import uuid

from django.conf import settings
from django.db import models


class AssistantThread(models.Model):
    """A saved conversation with the assistant: general (no sector) or one project's.

    The id comes from the client, so a conversation keeps the same id from its first
    message. `messages` holds what the screen shows: role, content, compact action
    receipts, choices and the request id that wrote it (to ignore replays)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assistant_threads",
    )
    sector = models.ForeignKey(
        "core.Sector",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="assistant_threads",
    )
    title = models.CharField(max_length=120)
    messages = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)
        indexes = [models.Index(fields=["user", "sector", "-updated_at"])]

    def __str__(self):
        return self.title
