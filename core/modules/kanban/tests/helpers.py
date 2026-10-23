from django.test import TestCase
from rest_framework.test import APIClient

from core.models.user import User
from core.modules.kanban.models.task import Status
from core.modules.organizations.models.organization import OrganizationMember
from core.modules.organizations.services.organization import OrganizationService

API = "/api/v1/"


def make_user(email):
    return User.objects.create_user(email=email, password="x12345678!", name="User")


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


class KanbanTestCase(TestCase):
    """An organization with an owner (self.client) and a plain member."""

    def setUp(self):
        self.owner = make_user("owner@a.com")
        self.org = OrganizationService.create(self.owner, name="Acme")
        self.client = client_for(self.owner)
        self.member = self.add_org_member("member@a.com", "member")
        self.member_client = client_for(self.member)

    def add_org_member(self, email, role="member"):
        user = make_user(email)
        OrganizationMember.objects.create(organization=self.org, user=user, role=role)
        return user

    def make_sector(self, client=None, **data):
        res = (client or self.client).post(
            f"{API}organizations/{self.org.id}/sectors/", {"name": "Board", **data}
        )
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()["id"]

    def share_sector(self, sector_id, user, role="editor"):
        res = self.client.post(
            f"{API}sectors/{sector_id}/members/",
            {"user_id": str(user.id), "role": role},
        )
        self.assertEqual(res.status_code, 201, res.content)

    def status_ids(self, sector_id):
        return {s.name: str(s.id) for s in Status.objects.filter(sector_id=sector_id)}

    def make_task(self, sector_id, client=None, **data):
        res = (client or self.client).post(
            f"{API}sectors/{sector_id}/tasks/", {"title": "Task", **data}
        )
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()
