from auditlog.models import LogEntry
from django.test import TestCase

from core.models.user import User, UserSession


class AuditLogTests(TestCase):
    def test_logs_jwt_user_as_actor(self):
        user = User.objects.create_user("a@a.com", "S3cure-pass!", name="A")
        self.client.post(
            "/api/v1/login/", {"email": "a@a.com", "password": "S3cure-pass!"}
        )

        response = self.client.post("/api/v1/me/logout/")

        self.assertEqual(response.status_code, 200)
        entry = LogEntry.objects.get_for_model(UserSession).latest("timestamp")
        self.assertEqual(entry.actor, user)
