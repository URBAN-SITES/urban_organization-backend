import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.modules.chat.models.chat import ChatMessage
from core.modules.kanban.models.sector import Sector
from core.modules.kanban.models.task import Comment, Task
from core.modules.organizations.models.organization import Organization

TARGETS = ("sector", "task", "comment", "message")


# [P2-I] File stored in Cloudinary (UploadService). At most one target;
# none = organization document. `message` depends on P2-H (chat).
class Attachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name=_("organization"),
    )
    sector = models.ForeignKey(
        Sector,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attachments",
        verbose_name=_("sector"),
    )
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attachments",
        verbose_name=_("task"),
    )
    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attachments",
        verbose_name=_("comment"),
    )
    message = models.ForeignKey(
        ChatMessage,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attachments",
        verbose_name=_("message"),
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="+",
        verbose_name=_("uploaded by"),
    )
    url = models.URLField(_("url"), max_length=2048)
    storage_key = models.CharField(
        _("storage key"),
        max_length=512,
        unique=True,
        help_text=_("Cloudinary public_id; needed to delete the file."),
    )
    file_name = models.CharField(_("file name"), max_length=255)
    mime_type = models.CharField(_("mime type"), max_length=100)
    size_bytes = models.PositiveBigIntegerField(_("size in bytes"))
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("attachment")
        verbose_name_plural = _("attachments")
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                name="attachment_at_most_one_target",
                condition=(
                    models.Q(**{f"{t}__isnull": True for t in TARGETS})
                    | models.Q(
                        sector__isnull=False,
                        task__isnull=True,
                        comment__isnull=True,
                        message__isnull=True,
                    )
                    | models.Q(
                        sector__isnull=True,
                        task__isnull=False,
                        comment__isnull=True,
                        message__isnull=True,
                    )
                    | models.Q(
                        sector__isnull=True,
                        task__isnull=True,
                        comment__isnull=False,
                        message__isnull=True,
                    )
                    | models.Q(
                        sector__isnull=True,
                        task__isnull=True,
                        comment__isnull=True,
                        message__isnull=False,
                    )
                ),
            )
        ]

    def __str__(self) -> str:
        return self.file_name
