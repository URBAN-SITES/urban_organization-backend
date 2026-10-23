from datetime import timedelta
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import requests
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models.user import User
from core.modules.calendar_sync.models.calendar import UserIntegration
from core.modules.calendar_sync.services.google import (
    SCOPE_CALENDAR,
    SCOPE_DRIVE,
    GoogleCalendarService,
)
from core.modules.kanban.models.resource_link import ResourceLink
from core.modules.kanban.services.sector import SectorService
from core.modules.kanban.services.task import TaskService
from core.modules.organizations.services.organization import OrganizationService

REQUEST = "core.modules.calendar_sync.services.drive.requests.request"
API = "/api/v1/integrations/google/"
ENV = {"GOOGLE_CLIENT_ID": "client-id", "GOOGLE_CLIENT_SECRET": "secret"}
FILE_ID = "1AbCdEfGhIjKlMnOpQrStUv"


def reply(status=200, data=None):
    response = MagicMock(status_code=status, ok=status < 400)
    response.json.return_value = data or {}
    return response


class FakeDrive:
    """Stands in for the Drive API: remembers calls and answers by method + path."""

    def __init__(self, folder=None, status=200, file=None):
        self.calls = []
        self.folder = folder
        self.status = status
        self.file = file or {
            "id": FILE_ID,
            "name": "ata.pdf",
            "mimeType": "application/pdf",
            "size": "12",
            "webViewLink": f"https://drive.google.com/file/d/{FILE_ID}/view",
            "modifiedTime": "2026-10-23T12:00:00.000Z",
        }

    def __call__(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.status != 200:
            return reply(self.status)
        if (
            method == "GET"
            and url.endswith("/files")
            and "mimeType = " in kwargs["params"]["q"]
        ):
            return reply(200, {"files": [{"id": self.folder}] if self.folder else []})
        if method == "POST" and "upload/drive" in url:  # must come before "/files"
            return reply(200, self.file)
        if method == "POST" and url.endswith("/files"):  # create folder
            self.folder = "FOLDER1"
            return reply(200, {"id": "FOLDER1"})
        if method == "POST" and url.endswith("/permissions"):
            return reply(200, {"id": "perm"})
        if method == "GET" and url.endswith("/files"):  # list inside the folder
            return reply(200, {"files": [self.file]})
        if method == "GET" and "/files/" in url:
            return reply(200, self.file)
        return reply(404)

    def made(self, method, fragment):
        return [c for c in self.calls if c[0] == method and fragment in c[1]]


class DriveTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("o@a.com", "x12345678!", name="Owner")
        self.org = OrganizationService.create(self.owner, name="Acme")
        self.sector = SectorService.create(self.owner, self.org.id, name="Dev")
        self.task = TaskService.create(self.owner, self.sector.id, {"title": "Ship"})
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.connect(self.owner)

    def connect(self, user, scopes=(SCOPE_CALENDAR, SCOPE_DRIVE)):
        UserIntegration.objects.update_or_create(
            user=user,
            provider="google_calendar",
            defaults={
                "access_token": "AT",
                "refresh_token": "RT",
                "scopes": list(scopes),
                "expires_at": timezone.now() + timedelta(hours=1),
                "status": "active",
            },
        )

    def pdf(self, name="ata.pdf", size=12):
        return SimpleUploadedFile(name, b"x" * size, content_type="application/pdf")

    def upload(self, fake, **extra):
        with patch(REQUEST, side_effect=fake):
            return self.client.post(
                f"{API}drive/upload/", {"file": self.pdf(), **extra}, format="multipart"
            )


class AuthorizeAndStatusTests(DriveTestCase):
    def test_drive_scope_is_only_requested_when_asked(self):
        with patch.dict("os.environ", ENV):
            plain = self.client.get(f"{API}authorize/").json()["url"]
            drive = self.client.get(f"{API}authorize/?drive=true").json()["url"]
        plain_scope = parse_qs(urlparse(plain).query)["scope"][0]
        drive_query = parse_qs(urlparse(drive).query)
        self.assertEqual(plain_scope, SCOPE_CALENDAR)
        self.assertEqual(drive_query["scope"][0].split(), [SCOPE_CALENDAR, SCOPE_DRIVE])
        self.assertEqual(drive_query["include_granted_scopes"], ["true"])

    def test_status_reports_drive_access(self):
        self.assertEqual(
            self.client.get(API).json(), {"connected": True, "drive": True}
        )
        self.connect(self.owner, scopes=(SCOPE_CALENDAR,))
        self.assertEqual(
            self.client.get(API).json(), {"connected": True, "drive": False}
        )

    def test_legacy_connection_without_scopes_still_does_meet_but_not_drive(self):
        integration = UserIntegration.objects.get(user=self.owner)
        integration.scopes = []
        integration.save()
        self.assertTrue(GoogleCalendarService.has_scope(integration, SCOPE_CALENDAR))
        self.assertFalse(GoogleCalendarService.has_scope(integration, SCOPE_DRIVE))


class UploadTests(DriveTestCase):
    def test_first_upload_creates_the_folder_and_sends_a_multipart_body(self):
        fake = FakeDrive()
        res = self.upload(fake)
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.json()["file"]["name"], "ata.pdf")
        self.assertEqual(res.json()["file"]["size_bytes"], 12)
        self.assertIsNone(res.json()["link"])
        self.assertEqual(len(fake.made("POST", "/files")), 2)  # folder + upload
        sent = fake.made("POST", "upload/drive")[0][2]
        self.assertEqual(sent["headers"]["Authorization"], "Bearer AT")
        self.assertTrue(
            sent["headers"]["Content-Type"].startswith("multipart/related; boundary=")
        )
        self.assertIn(b'"parents": ["FOLDER1"]', sent["data"])
        self.assertIn(b'"name": "ata.pdf"', sent["data"])
        self.assertIn(b"x" * 12, sent["data"])
        self.assertEqual(fake.made("POST", "/permissions"), [])  # private by default

    def test_existing_folder_is_reused(self):
        fake = FakeDrive(folder="FOLDER0")
        self.upload(fake)
        created_folder = [
            c for c in fake.made("POST", "/files") if "upload" not in c[1]
        ]
        self.assertEqual(created_folder, [])
        self.assertIn(
            b'"parents": ["FOLDER0"]', fake.made("POST", "upload/drive")[0][2]["data"]
        )

    def test_share_link_adds_a_public_reader_permission(self):
        fake = FakeDrive(folder="F")
        res = self.upload(fake, share_link="true")
        self.assertTrue(res.json()["file"]["shared_with_link"])
        permission = fake.made("POST", "/permissions")[0][2]["json"]
        self.assertEqual(permission, {"type": "anyone", "role": "reader"})

    def test_too_big_file_never_reaches_google(self):
        fake = FakeDrive()
        with patch(REQUEST, side_effect=fake):
            res = self.client.post(
                f"{API}drive/upload/",
                {"file": self.pdf(size=10 * 1024 * 1024 + 1)},
                format="multipart",
            )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(fake.calls, [])

    def test_upload_to_a_task_also_attaches_the_link(self):
        res = self.upload(FakeDrive(folder="F"), task=str(self.task.id))
        self.assertEqual(res.status_code, 201, res.content)
        link = ResourceLink.objects.get(task=self.task)
        self.assertEqual((link.title, link.created_by), ("ata.pdf", self.owner))
        self.assertTrue(link.url.startswith("https://drive.google.com/file/d/"))
        self.assertEqual(res.json()["link"]["id"], str(link.id))

    def test_viewer_cannot_attach_and_google_is_not_called(self):
        viewer = User.objects.create_user("v@a.com", "x12345678!", name="V")
        OrganizationService.add_member(self.owner, self.org.id, "v@a.com", "member")
        SectorService.add_member(self.owner, self.sector.id, viewer.id, "viewer")
        self.connect(viewer)
        client = APIClient()
        client.force_authenticate(viewer)
        fake = FakeDrive(folder="F")
        with patch(REQUEST, side_effect=fake):
            res = client.post(
                f"{API}drive/upload/",
                {"file": self.pdf(), "task": str(self.task.id)},
                format="multipart",
            )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(fake.calls, [])
        self.assertFalse(ResourceLink.objects.exists())


class ListAndAttachTests(DriveTestCase):
    def test_list_returns_the_files_and_escapes_the_search(self):
        fake = FakeDrive(folder="F")
        with patch(REQUEST, side_effect=fake):
            res = self.client.get(f"{API}drive/files/", {"q": "o'neil"})
        self.assertEqual([f["name"] for f in res.json()], ["ata.pdf"])
        query = fake.made("GET", "/files")[-1][2]["params"]["q"]
        self.assertIn("'F' in parents", query)
        self.assertIn("name contains 'o\\'neil'", query)

    def test_list_is_empty_when_the_folder_does_not_exist_yet(self):
        with patch(REQUEST, side_effect=FakeDrive()):
            self.assertEqual(self.client.get(f"{API}drive/files/").json(), [])

    def test_attach_creates_a_link_to_the_task(self):
        with patch(REQUEST, side_effect=FakeDrive(folder="F")):
            res = self.client.post(
                f"{API}drive/attach/", {"task": str(self.task.id), "file_id": FILE_ID}
            )
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(ResourceLink.objects.get(task=self.task).title, "ata.pdf")

    def test_file_id_is_validated_before_it_reaches_the_url(self):
        fake = FakeDrive()
        with patch(REQUEST, side_effect=fake):
            for bad in ("../../etc", "a/b", "short", "x" * 200):
                res = self.client.post(
                    f"{API}drive/attach/", {"task": str(self.task.id), "file_id": bad}
                )
                self.assertEqual(res.status_code, 400, bad)
        self.assertEqual(fake.calls, [])

    def test_google_errors_map_to_clear_statuses(self):
        body = {"task": str(self.task.id), "file_id": FILE_ID}
        with patch(REQUEST, side_effect=FakeDrive(status=404)):
            self.assertEqual(
                self.client.post(f"{API}drive/attach/", body).status_code, 404
            )
        with patch(REQUEST, side_effect=FakeDrive(status=403)):
            self.assertEqual(
                self.client.post(f"{API}drive/attach/", body).status_code, 400
            )
        with patch(REQUEST, side_effect=FakeDrive(status=500)):
            self.assertEqual(
                self.client.post(f"{API}drive/attach/", body).status_code, 502
            )
        with patch(REQUEST, side_effect=requests.ConnectionError()):
            self.assertEqual(
                self.client.post(f"{API}drive/attach/", body).status_code, 502
            )
        self.assertEqual(
            UserIntegration.objects.get().status, "active"
        )  # 403/404 are per file

    def test_rejected_token_disconnects_the_account(self):
        with patch(REQUEST, side_effect=FakeDrive(status=401)):
            res = self.client.post(
                f"{API}drive/attach/", {"task": str(self.task.id), "file_id": FILE_ID}
            )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(UserIntegration.objects.get().status, "revoked")


class AccessTests(DriveTestCase):
    def test_not_connected_or_without_drive_scope_never_calls_google(self):
        fake = FakeDrive(folder="F")
        self.connect(self.owner, scopes=(SCOPE_CALENDAR,))
        with patch(REQUEST, side_effect=fake):
            for res in (self.client.get(f"{API}drive/files/"), self.upload(fake)):
                self.assertEqual(res.status_code, 400)
        UserIntegration.objects.all().delete()
        with patch(REQUEST, side_effect=fake):
            self.assertEqual(self.client.get(f"{API}drive/files/").status_code, 400)
        self.assertEqual(fake.calls, [])

    def test_anonymous_is_rejected(self):
        for method, path in (
            ("get", "drive/files/"),
            ("post", "drive/upload/"),
            ("post", "drive/attach/"),
        ):
            self.assertEqual(
                getattr(APIClient(), method)(f"{API}{path}").status_code, 401
            )
