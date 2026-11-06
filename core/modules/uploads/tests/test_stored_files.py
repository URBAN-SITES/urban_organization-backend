from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from core.modules.chat.tests.test_chat import API, PUSH, ChatTestCase
from core.modules.uploads.models.stored_file import StoredFile
from core.modules.uploads.services.upload import UploadService

VOICE = b"\x1aE\xdf\xa3" + b"\x00" * 256  # webm header


def voice_file():
    return SimpleUploadedFile("audio-1.webm", VOICE, content_type="audio/webm")


@patch.object(UploadService, "cloudinary_ready", return_value=False)
@patch(PUSH)
class StoredFileTests(ChatTestCase):
    def test_voice_message_without_cloudinary_is_kept_and_served(self, _push, _ready):
        channel = self.general(self.ana)["id"]
        res = self.clients[self.ana].post(
            f"{API}chat/channels/{channel}/messages/",
            {"content": "", "files": [voice_file()]},
            format="multipart",
        )
        self.assertEqual(res.status_code, 201, res.content)
        attachment = res.json()["attachments"][0]
        self.assertEqual(attachment["mime_type"], "audio/webm")
        self.assertTrue(attachment["url"].startswith("/api/v1/uploads/files/"))

        served = APIClient().get(attachment["url"])  # the link is the key
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served.content, VOICE)
        self.assertEqual(served["Content-Type"], "audio/webm")
        self.assertTrue(served["Content-Disposition"].startswith("inline"))
        self.assertEqual(served["Content-Security-Policy"], "sandbox")

    def test_deleting_the_message_removes_the_stored_file(self, _push, _ready):
        channel = self.general(self.ana)["id"]
        message = (
            self.clients[self.ana]
            .post(
                f"{API}chat/channels/{channel}/messages/",
                {"content": "", "files": [voice_file()]},
                format="multipart",
            )
            .json()
        )
        self.clients[self.ana].delete(f"{API}chat/messages/{message['id']}/")
        self.assertFalse(StoredFile.objects.exists())

    def test_other_types_download_instead_of_opening(self, _push, _ready):
        result = UploadService.upload(
            SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")
        )
        served = APIClient().get(result["url"])
        self.assertTrue(served["Content-Disposition"].startswith("attachment"))

    def test_cloudinary_is_used_when_configured(self, _push, _ready):
        with (
            patch.object(UploadService, "cloudinary_ready", return_value=True),
            patch(
                "cloudinary.uploader.upload",
                return_value={"secure_url": "https://cdn/x", "public_id": "u/x"},
            ),
        ):
            result = UploadService.upload(voice_file())
        self.assertEqual(result, {"url": "https://cdn/x", "public_id": "u/x"})
        self.assertFalse(StoredFile.objects.exists())

    def test_cloudinary_misconfigured_is_a_clear_error_not_a_crash(self, _push, _ready):
        with (
            patch.object(UploadService, "cloudinary_ready", return_value=True),
            patch("cloudinary.uploader.upload", side_effect=ValueError("no key")),
        ):
            channel = self.general(self.ana)["id"]
            res = self.clients[self.ana].post(
                f"{API}chat/channels/{channel}/messages/",
                {"content": "", "files": [voice_file()]},
                format="multipart",
            )
        self.assertEqual(res.status_code, 500)
        self.assertIn("Upload failed", res.json()["detail"])


class CloudinaryReadyTests(ChatTestCase):
    def test_placeholder_from_env_example_is_not_a_key(self):
        with patch("cloudinary.config") as config:
            config.return_value.api_secret = "<api_secret>"
            self.assertFalse(UploadService.cloudinary_ready())
            config.return_value.api_secret = "real-secret"
            self.assertTrue(UploadService.cloudinary_ready())
