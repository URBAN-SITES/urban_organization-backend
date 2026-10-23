from django.test import TestCase
from rest_framework.test import APIClient

from core.models.user import User
from core.modules.organizations.services.organization import OrganizationService


class WorkspaceOnboardingTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="workspace@example.invalid", password="Workspace-test!2026"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_workspace_address_size_and_logo_are_saved(self):
        response = self.client.post(
            "/api/v1/organizations/",
            {
                "name": "Norte",
                "slug": "norte-studio",
                "team_size": "11-50",
                "logo_url": "https://example.invalid/logo.png",
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["team_size"], "11-50")
        self.assertEqual(
            response.json()["logo_url"], "https://example.invalid/logo.png"
        )
        address = self.client.get("/api/v1/organizations/by-slug/norte-studio/")
        self.assertEqual(address.status_code, 200)
        self.assertEqual(address.json()["id"], response.json()["id"])
        self.assertEqual(
            self.client.post(
                "/api/v1/organizations/", {"name": "Duplicate", "slug": "norte-studio"}
            ).status_code,
            400,
        )

    def test_workspace_address_does_not_expose_another_organization(self):
        other = User.objects.create_user(
            email="other-workspace@example.invalid", password="Workspace-test!2026"
        )
        OrganizationService.create(other, name="Private", slug="private-workspace")
        self.assertEqual(
            self.client.get(
                "/api/v1/organizations/by-slug/private-workspace/"
            ).status_code,
            404,
        )

    def test_legacy_creation_still_works_and_new_fields_are_validated(self):
        first = OrganizationService.create(self.owner, name="Legacy")
        second = OrganizationService.create(self.owner, name="Legacy")
        self.assertNotEqual(first.slug, second.slug)
        for slug in ("UPPER", "a_b", "-start", "end-", "double--dash"):
            self.assertEqual(
                self.client.post(
                    "/api/v1/organizations/", {"name": "Invalid", "slug": slug}
                ).status_code,
                400,
            )
        self.assertEqual(
            self.client.post(
                "/api/v1/organizations/", {"name": "Invalid", "team_size": "unknown"}
            ).status_code,
            400,
        )
