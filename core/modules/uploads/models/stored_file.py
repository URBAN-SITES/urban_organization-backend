import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


# shortcut: bytes live in the database when Cloudinary is not configured (free hosting
# without a file store). Every upload is capped at 10 MB; set CLOUDINARY_URL to move new
# uploads to Cloudinary once volume grows.
class StoredFile(models.Model):
    """Content of an upload served by the API itself (UploadService fallback)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content = models.BinaryField(_("content"))
    file_name = models.CharField(_("file name"), max_length=255)
    mime_type = models.CharField(_("MIME type"), max_length=100)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("stored file")
        verbose_name_plural = _("stored files")

    def __str__(self) -> str:
        return self.file_name
