import cloudinary.uploader
from rest_framework import exceptions

from core.uploads.response_messages import MSG_UPLOAD_FAILED

# cloudinary reads its credentials from the CLOUDINARY_URL env var


class UploadService:
    @staticmethod
    def upload(file, folder: str = "uploads") -> dict:
        """Uploads any file (image, video, pdf...) and returns its public URL and id."""
        try:
            result = cloudinary.uploader.upload(
                file, folder=folder, resource_type="auto"
            )
        except cloudinary.exceptions.Error:
            raise exceptions.APIException(MSG_UPLOAD_FAILED)
        return {"url": result["secure_url"], "public_id": result["public_id"]}

    @staticmethod
    def delete(public_id: str) -> None:
        cloudinary.uploader.destroy(public_id)
