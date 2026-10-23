import logging

from rest_framework.exceptions import ValidationError

from core.models.user import User
from core.modules.uploads.models.attachment import Attachment
from core.modules.uploads.response_messages import (
    MSG_ATTACHMENT_TOO_BIG,
    MSG_ATTACHMENT_TOO_MANY,
)
from core.modules.uploads.services.upload import UploadService

logger = logging.getLogger(__name__)
MAX_FILES = 5
MAX_BYTES = 10 * 1024 * 1024


class AttachmentService:
    @staticmethod
    def validate(files) -> None:
        if len(files) > MAX_FILES:
            raise ValidationError(MSG_ATTACHMENT_TOO_MANY)
        if any(file.size > MAX_BYTES for file in files):
            raise ValidationError(MSG_ATTACHMENT_TOO_BIG)

    @staticmethod
    def upload_all(files, folder: str) -> list[dict]:
        """Uploads every file; if one fails, removes the ones already stored."""
        stored = []
        try:
            for file in files:
                result = UploadService.upload(file, folder=folder)
                stored.append(
                    {
                        "url": result["url"],
                        "storage_key": result["public_id"],
                        "file_name": file.name[:255],
                        "mime_type": (file.content_type or "application/octet-stream")[
                            :100
                        ],
                        "size_bytes": file.size,
                    }
                )
        except Exception:
            AttachmentService.discard(stored)
            raise
        return stored

    @staticmethod
    def discard(stored: list[dict]) -> None:
        for item in stored:
            try:
                UploadService.delete(item["storage_key"])
            except Exception:
                logger.exception("could not delete orphan file %s", item["storage_key"])

    @staticmethod
    def create_for_message(user: User, message, stored: list[dict]) -> None:
        Attachment.objects.bulk_create(
            Attachment(
                organization_id=message.channel.organization_id,
                message=message,
                uploaded_by=user,
                **item,
            )
            for item in stored
        )

    @staticmethod
    def delete_for_message(message) -> None:
        attachments = list(message.attachments.all())
        message.attachments.all().delete()
        AttachmentService.discard(
            [{"storage_key": attachment.storage_key} for attachment in attachments]
        )
