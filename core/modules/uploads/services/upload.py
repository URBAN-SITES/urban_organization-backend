from pathlib import PurePath

import cloudinary.uploader
from rest_framework import exceptions

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
    def upload(file, folder: str = "uploads") -> dict:
        """Uploads a file (image, video, pdf...) and returns its public URL and id."""
        UploadService.check_type(file)
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
