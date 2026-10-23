from django.test import TestCase
from rest_framework.test import APIClient

from core.models.user import User
from core.modules.organizations.services.organization import OrganizationService
from core.modules.teams.models.team import Team, TeamMember

PASSWORD = "x12345678!"


def make_user(email):
    return User.objects.create_user(email=email, password=PASSWORD, name="User")


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


class TeamTests(TestCase):
    def setUp(self):
        self.owner = make_user("owner@a.com")
        self.org = OrganizationService.create(self.owner, name="Acme")
        self.base = f"/api/v1/organizations/{self.org.id}/teams/"
        self.client = client_for(self.owner)
        self.member = make_user("m@a.com")
        self.other_member = make_user("m2@a.com")
        for user in (self.member, self.other_member):
            OrganizationService.add_member(
                self.owner, self.org.id, user.email, "member"
            )

    def create_team(self, name="Design"):
        res = self.client.post(self.base, {"name": name})
        self.assertEqual(res.status_code, 201)
        return res.json()["id"]

    def test_create_makes_creator_lead_and_name_is_unique(self):
        team_id = self.create_team()
        self.assertEqual(
            TeamMember.objects.get(team_id=team_id).role, TeamMember.Role.LEAD
        )
        self.assertEqual(
            self.client.post(self.base, {"name": "Design"}).status_code, 400
        )
        self.assertEqual(len(self.client.get(self.base).json()["results"]), 1)

    def test_only_admin_creates_and_deletes(self):
        self.assertEqual(
            client_for(self.member).post(self.base, {"name": "X"}).status_code, 403
        )
        team_id = self.create_team()
        member_client = client_for(self.member)
        self.assertEqual(member_client.get(f"{self.base}{team_id}/").status_code, 200)
        self.assertEqual(
            member_client.delete(f"{self.base}{team_id}/").status_code, 403
        )
        self.assertEqual(self.client.delete(f"{self.base}{team_id}/").status_code, 204)
        self.assertFalse(Team.objects.exists())
        self.create_team()  # name is free again

    def test_outsider_gets_404(self):
        team_id = self.create_team()
        outsider = client_for(make_user("out@a.com"))
        self.assertEqual(outsider.get(self.base).status_code, 404)
        self.assertEqual(outsider.get(f"{self.base}{team_id}/").status_code, 404)

    def test_add_member_requires_org_membership(self):
        team_id = self.create_team()
        url = f"{self.base}{team_id}/members/"
        outsider = make_user("out@a.com")
        res = self.client.post(url, {"user_id": str(outsider.id)})
        self.assertEqual(res.status_code, 400)
        res = self.client.post(url, {"user_id": str(self.member.id)})
        self.assertEqual(res.status_code, 201)
        res = self.client.post(url, {"user_id": str(self.member.id)})
        self.assertEqual(res.status_code, 400)

    def test_team_lead_manages_without_being_org_admin(self):
        team_id = self.create_team()
        url = f"{self.base}{team_id}/members/"
        res = self.client.post(url, {"user_id": str(self.member.id), "role": "lead"})
        lead_client = client_for(self.member)
        res = lead_client.post(url, {"user_id": str(self.other_member.id)})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(
            lead_client.patch(
                f"{self.base}{team_id}/", {"name": "Renamed"}
            ).status_code,
            200,
        )
        # plain team member cannot manage
        plain = client_for(self.other_member)
        self.assertEqual(
            plain.patch(f"{self.base}{team_id}/", {"name": "x"}).status_code, 403
        )

    def test_member_can_leave_team(self):
        team_id = self.create_team()
        url = f"{self.base}{team_id}/members/"
        member_id = self.client.post(url, {"user_id": str(self.member.id)}).json()["id"]
        other_id = self.client.post(url, {"user_id": str(self.other_member.id)}).json()[
            "id"
        ]
        member_client = client_for(self.member)
        self.assertEqual(member_client.delete(f"{url}{other_id}/").status_code, 403)
        self.assertEqual(member_client.delete(f"{url}{member_id}/").status_code, 204)

    def test_change_role(self):
        team_id = self.create_team()
        url = f"{self.base}{team_id}/members/"
        member_id = self.client.post(url, {"user_id": str(self.member.id)}).json()["id"]
        res = self.client.patch(f"{url}{member_id}/", {"role": "lead"})
        self.assertEqual(res.json()["role"], "lead")
