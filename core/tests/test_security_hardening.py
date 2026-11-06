import re
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from core.modules.github.views.github import GitHubWebhookView
from core.modules.kanban.tests.helpers import KanbanTestCase, client_for, make_user
from core.modules.meetings.views.meeting import LiveKitWebhookView
from core.modules.payments.views.payment import PaymentWebhookView
from core.tests.test_cross_tenant import api_routes

UPLOAD = "/api/v1/uploads/"
FAKE = {
    "uuid": "00000000-0000-0000-0000-000000000001",
    "int": "1",
    "slug": "acme",
    "str": "x",
}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

# Reached without a session on purpose (login, sign-up, webhooks, invite preview...).
PUBLIC = {
    "api/v1/csrf/",
    "api/v1/login/",
    "api/v1/login/google/",
    "api/v1/registration/request/",
    "api/v1/registration/verify/",
    "api/v1/registration/confirm/",
    "api/v1/password-reset/request/",
    "api/v1/password-reset/verify/",
    "api/v1/password-reset/confirm/",
    "api/v1/refresh/",
    "api/v1/payments/webhook/",
    "api/v1/invitations/preview/",
    "api/v1/integrations/github/authorize/",
    "api/v1/integrations/github/callback/",
    "api/v1/integrations/github/webhook/",
    "api/v1/meetings/livekit/webhook/",
    # uploads kept in the database: the random id is the key, like a Cloudinary URL
    "api/v1/uploads/files/<uuid:file_id>/",
    # read-only board behind a project's public link (token in the path)
    "api/v1/public/projects/<str:token>/",
}


class AnonymousAccessTest(TestCase):
    def test_every_private_route_refuses_anonymous_requests(self):
        client = APIClient()
        opened, checked = [], 0
        for route in api_routes():
            if route in PUBLIC:
                continue
            url = "/" + re.sub(r"<(\w+):\w+>", lambda m: FAKE[m.group(1)], route)
            res = client.get(url)
            checked += 1
            if res.status_code not in (401, 403, 405):
                opened.append(f"{route} -> {res.status_code}")
        self.assertGreater(checked, 100)
        self.assertEqual(opened, [])

    def test_ai_test_page_is_not_served_outside_debug(self):
        self.assertEqual(APIClient().get("/api/v1/ai/test/").status_code, 404)


class UploadTypeTest(TestCase):
    def setUp(self):
        self.client = client_for(make_user("up@a.com"))

    def post(self, name, content, content_type="application/octet-stream"):
        file = SimpleUploadedFile(name, content, content_type=content_type)
        return self.client.post(UPLOAD, {"file": file}, format="multipart")

    @patch("cloudinary.uploader.upload")
    def test_pages_scripts_and_programs_are_refused(self, upload):
        cases = [
            ("page.html", b"<html><script>alert(1)</script></html>"),
            ("logo.svg", b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"),
            ("photo.png", b"  <!DOCTYPE html><p>disfarcado</p>"),
            ("setup.png", b"MZ\x90\x00programa"),
            ("run.sh", b"echo oi"),
        ]
        for name, content in cases:
            res = self.post(name, content)
            self.assertEqual(res.status_code, 400, name)
        upload.assert_not_called()

    @patch(
        "core.modules.uploads.services.upload.UploadService.cloudinary_ready",
        return_value=True,
    )
    @patch(
        "cloudinary.uploader.upload",
        return_value={
            "secure_url": "https://res.cloudinary.com/x.png",
            "public_id": "x",
        },
    )
    def test_regular_files_still_upload(self, upload, _ready):
        self.assertEqual(self.post("foto.png", PNG, "image/png").status_code, 201)
        self.assertEqual(
            self.post("notas.pdf", b"%PDF-1.7\n", "application/pdf").status_code, 201
        )
        self.assertEqual(upload.call_count, 2)


class WebhookThrottleTest(TestCase):
    def test_webhooks_use_their_own_rate_bucket(self):
        for view in (GitHubWebhookView, LiveKitWebhookView, PaymentWebhookView):
            self.assertEqual(view.throttle_scope, "webhook", view.__name__)
            self.assertTrue(view.throttle_classes, view.__name__)


class UserVisibilityTest(KanbanTestCase):
    def test_people_of_the_same_organization_see_each_other(self):
        res = self.member_client.get("/api/v1/users/list/")
        self.assertEqual(res.status_code, 200)
        emails = {row["email"] for row in res.json()["results"]}
        self.assertEqual(emails, {"owner@a.com", "member@a.com"})
        res = self.member_client.get(f"/api/v1/users/{self.owner.id}/")
        self.assertEqual(res.status_code, 200)
