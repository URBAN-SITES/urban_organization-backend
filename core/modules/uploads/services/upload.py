from pathlib import PurePath

import cloudinary.uploader
from rest_framework import exceptions

from core.modules.uploads.models.stored_file import StoredFile
from core.modules.uploads.response_messages import (
    MSG_FILE_TYPE_BLOCKED,
    MSG_UPLOAD_FAILED,
)

# cloudinary reads its credentials from the CLOUDINARY_URL env var

# Served back as-is from a public URL: pages and SVG can run scripts, the rest are programs.
BLOCKED_EXTENSIONS = {
    ".htm", ".html", ".xhtml", ".shtml", ".svg", ".svgz", ".xml", ".js", ".mjs",
    ".php", ".exe", ".dll", ".msi", ".com", ".scr", ".bat", ".cmd", ".ps1",
    ".vbs", ".sh", ".jar", ".apk",
}  # fmt: skip
# Checked on the first bytes too, so renaming page.html to page.png does not help.
BLOCKED_SIGNATURES = (
    b"<!doctype html",
    b"<html",
    b"<script",
    b"<svg",
    b"<?xml",
    b"<?php",
)
BLOCKED_MAGIC = (b"MZ", b"\x7fELF")
DB_PREFIX = "db:"  # storage_key of files kept in the database


class UploadService:
    @staticmethod
    def check_type(file) -> None:
        """Refuses web pages, SVG, scripts and executables, by name and by content."""
        if PurePath(file.name or "").suffix.lower() in BLOCKED_EXTENSIONS:
            raise exceptions.ValidationError({"file": MSG_FILE_TYPE_BLOCKED})
        head = file.read(1024)
        file.seek(0)
        if head.startswith(BLOCKED_MAGIC) or any(
            sig in head.lstrip().lower() for sig in BLOCKED_SIGNATURES
        ):
            raise exceptions.ValidationError({"file": MSG_FILE_TYPE_BLOCKED})

    @staticmethod
    def cloudinary_ready() -> bool:
        # the .env.example placeholder (cloudinary://<api_key>:<api_secret>@...) is not a key
        secret = cloudinary.config().api_secret or ""
        return bool(secret) and "<" not in secret

    @staticmethod
    def upload(file, folder: str = "uploads") -> dict:
        """Uploads a file (image, video, pdf...) and returns its public URL and id.

        Without CLOUDINARY_URL the file is kept in the database and served by the API
        (`/api/v1/uploads/files/<id>/`), so uploads work on free hosting too."""
        UploadService.check_type(file)
        if not UploadService.cloudinary_ready():
            stored = StoredFile.objects.create(
                content=file.read(),
                file_name=(file.name or "file")[:255],
                mime_type=(file.content_type or "application/octet-stream")[:100],
            )
            return {
                "url": f"/api/v1/uploads/files/{stored.pk}/",
                "public_id": f"{DB_PREFIX}{stored.pk}",
            }
        try:
            result = cloudinary.uploader.upload(
                file, folder=folder, resource_type="auto"
            )
        except cloudinary.exceptions.Error, ValueError:
            raise exceptions.APIException(MSG_UPLOAD_FAILED)
        return {"url": result["secure_url"], "public_id": result["public_id"]}

    @staticmethod
    def delete(public_id: str) -> None:
        if public_id.startswith(DB_PREFIX):
            StoredFile.objects.filter(pk=public_id.removeprefix(DB_PREFIX)).delete()
            return
        cloudinary.uploader.destroy(public_id)
