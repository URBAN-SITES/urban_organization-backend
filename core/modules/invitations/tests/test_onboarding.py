import re
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.core import mail
from django.test import TestCase
from rest_framework.test import APIClient

from core.models.user import User
from core.modules.invitations.models.invite import OrganizationInvite
from core.modules.invitations.services.invite import InviteService
from core.modules.organizations.models.organization import OrganizationMember
from core.modules.organizations.services.organization import OrganizationService

PASSWORD = "Invite-register-pass!2026"
VERIFY = "core.services.google_auth.id_token.verify_oauth2_token"


class InvitationOnboardingTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.invalid", password=PASSWORD
        )
        self.organization = OrganizationService.create(self.owner, name="Onboarding")
        self.client = APIClient()

    def invite(self, email):
        with self.captureOnCommitCallbacks(execute=True):
            InviteService.create(self.owner, self.organization.id, email, "member")
        link = re.search(r"https?://\S+", mail.outbox[-1].body).group()
        return parse_qs(urlparse(link).query)["token"][0]

    def assert_accepted(self, token, email):
        self.assertFalse(
            OrganizationMember.objects.filter(
                organization=self.organization, user__email=email
            ).exists()
        )
        response = self.client.post("/api/v1/invitations/accept/", {"token": token})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["organization_id"], str(self.organization.pk))
        self.assertTrue(
            OrganizationMember.objects.filter(
                organization=self.organization, user__email=email, role="member"
            ).exists()
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/invitations/accept/", {"token": token}
            ).status_code,
            400,
        )

    def test_new_email_registration_login_then_explicit_acceptance(self):
        email = "new@example.invalid"
        token = self.invite(email)
        self.assertFalse(User.objects.filter(email=email).exists())
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/api/v1/registration/request/", {"email": email}
            )
        self.assertEqual(response.status_code, 201)
        code = re.search(r"\b\d{6}\b", mail.outbox[-1].body).group()
        response = self.client.post(
            "/api/v1/registration/confirm/",
            {"email": email, "code": code, "name": "Invited", "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            self.client.post(
                "/api/v1/login/", {"email": email, "password": PASSWORD}
            ).status_code,
            200,
        )
        self.assert_accepted(token, email)

    def test_existing_account_login_then_acceptance(self):
        email = "existing@example.invalid"
        User.objects.create_user(email=email, password=PASSWORD)
        token = self.invite(email)
        self.assertEqual(
            self.client.post(
                "/api/v1/login/", {"email": email, "password": PASSWORD}
            ).status_code,
            200,
        )
        self.assert_accepted(token, email)

    def test_google_new_and_existing_accounts_then_acceptance(self):
        for existing in (False, True):
            email = f"google-{existing}@example.invalid"
            self.client = APIClient()
            if existing:
                User.objects.create_user(email=email, password=PASSWORD)
            token = self.invite(email)
            with patch(
                VERIFY,
                return_value={
                    "email": email,
                    "email_verified": True,
                    "name": "Google Guest",
                },
            ):
                response = self.client.post(
                    "/api/v1/login/google/", {"credential": "test-credential"}
                )
            self.assertEqual(response.status_code, 200)
            self.assert_accepted(token, email)

    def test_google_with_different_email_does_not_consume_invite(self):
        token = self.invite("invited@example.invalid")
        with patch(
            VERIFY,
            return_value={"email": "other@example.invalid", "email_verified": True},
        ):
            self.assertEqual(
                self.client.post(
                    "/api/v1/login/google/", {"credential": "test-credential"}
                ).status_code,
                200,
            )
        self.assertEqual(
            self.client.post(
                "/api/v1/invitations/accept/", {"token": token}
            ).status_code,
            400,
        )
        self.assertEqual(OrganizationInvite.objects.get().status, "pending")
