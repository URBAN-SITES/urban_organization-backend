from django.test import TestCase
from rest_framework.test import APIClient

from core.models.user import User
from core.modules.organizations.models.organization import (
    Organization,
    OrganizationMember,
)

PASSWORD = "x12345678!"
URL = "/api/v1/organizations/"


def make_user(email, name="User"):
    return User.objects.create_user(email=email, password=PASSWORD, name=name)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


class OrganizationTests(TestCase):
    def setUp(self):
        self.owner = make_user("owner@a.com", "Owner")
        self.client = client_for(self.owner)

    def create_org(self, name="Acme"):
        res = self.client.post(URL, {"name": name})
        self.assertEqual(res.status_code, 201)
        return res.json()["id"]

    def test_list_creates_personal_organization_once(self):
        for _ in range(2):
            results = self.client.get(URL).json()["results"]
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["is_personal"])
        self.assertEqual(OrganizationMember.objects.get(user=self.owner).role, "owner")

    def test_create_makes_caller_owner(self):
        org_id = self.create_org()
        member = OrganizationMember.objects.get(organization_id=org_id)
        self.assertEqual((member.user, member.role), (self.owner, "owner"))

    def test_current_role_is_scoped_to_caller_and_read_only(self):
        response = self.client.post(URL, {"name": "Roles", "current_role": "viewer"})
        self.assertEqual(response.json()["current_role"], "owner")
        org_id = response.json()["id"]
        viewer = make_user("role-viewer@a.com")
        OrganizationMember.objects.create(
            organization_id=org_id, user=viewer, role="viewer"
        )
        viewer_client = client_for(viewer)
        self.assertEqual(
            viewer_client.get(f"{URL}{org_id}/").json()["current_role"], "viewer"
        )
        roles = {
            item["id"]: item["current_role"]
            for item in viewer_client.get(URL).json()["results"]
        }
        self.assertEqual(roles[org_id], "viewer")
        self.assertEqual(
            self.client.patch(f"{URL}{org_id}/", {"name": "Renamed"}).json()[
                "current_role"
            ],
            "owner",
        )

    def test_non_member_gets_404(self):
        org_id = self.create_org()
        outsider = client_for(make_user("out@a.com"))
        self.assertEqual(outsider.get(f"{URL}{org_id}/").status_code, 404)
        self.assertEqual(outsider.get(f"{URL}{org_id}/members/").status_code, 404)

    def test_update_needs_admin(self):
        org_id = self.create_org()
        member = make_user("m@a.com")
        self.client.post(f"{URL}{org_id}/members/", {"email": "m@a.com"})
        res = client_for(member).patch(f"{URL}{org_id}/", {"name": "Hacked"})
        self.assertEqual(res.status_code, 403)
        res = self.client.patch(f"{URL}{org_id}/", {"name": "Renamed"})
        self.assertEqual(res.json()["name"], "Renamed")

    def test_delete_is_owner_only_and_soft_and_not_personal(self):
        org_id = self.create_org()
        admin = make_user("adm@a.com")
        self.client.post(
            f"{URL}{org_id}/members/", {"email": "adm@a.com", "role": "admin"}
        )
        self.assertEqual(client_for(admin).delete(f"{URL}{org_id}/").status_code, 403)
        self.assertEqual(self.client.delete(f"{URL}{org_id}/").status_code, 204)
        self.assertFalse(Organization.objects.get(id=org_id).is_active)
        self.assertEqual(self.client.get(f"{URL}{org_id}/").status_code, 404)

        personal = self.client.get(URL).json()["results"][0]["id"]
        self.assertEqual(self.client.delete(f"{URL}{personal}/").status_code, 400)

    def test_add_member_rules(self):
        org_id = self.create_org()
        members_url = f"{URL}{org_id}/members/"
        make_user("m@a.com")
        self.assertEqual(
            self.client.post(members_url, {"email": "M@A.com"}).status_code, 201
        )
        self.assertEqual(
            self.client.post(members_url, {"email": "m@a.com"}).status_code, 400
        )
        self.assertEqual(
            self.client.post(members_url, {"email": "ghost@a.com"}).status_code, 400
        )
        res = self.client.post(members_url, {"email": "m@a.com", "role": "owner"})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(len(self.client.get(members_url).json()["results"]), 2)

    def test_admin_cannot_grant_admin_or_touch_admin_or_owner(self):
        org_id = self.create_org()
        members_url = f"{URL}{org_id}/members/"
        admin = make_user("adm@a.com")
        other_admin = make_user("adm2@a.com")
        make_user("m@a.com")
        self.client.post(members_url, {"email": "adm@a.com", "role": "admin"})
        self.client.post(members_url, {"email": "adm2@a.com", "role": "admin"})
        regular = self.client.post(members_url, {"email": "m@a.com"}).json()
        admin_client = client_for(admin)

        res = admin_client.post(members_url, {"email": "m@a.com", "role": "admin"})
        self.assertEqual(res.status_code, 403)
        res = admin_client.patch(f"{members_url}{regular['id']}/", {"role": "admin"})
        self.assertEqual(res.status_code, 403)
        res = admin_client.patch(f"{members_url}{regular['id']}/", {"role": "viewer"})
        self.assertEqual(res.json()["role"], "viewer")

        admin2_id = OrganizationMember.objects.get(user=other_admin).id
        owner_id = OrganizationMember.objects.get(user=self.owner).id
        self.assertEqual(
            admin_client.delete(f"{members_url}{admin2_id}/").status_code, 403
        )
        self.assertEqual(
            admin_client.delete(f"{members_url}{owner_id}/").status_code, 403
        )

    def test_member_can_leave_but_owner_cannot(self):
        org_id = self.create_org()
        members_url = f"{URL}{org_id}/members/"
        member = make_user("m@a.com")
        self.client.post(members_url, {"email": "m@a.com"})
        member_id = OrganizationMember.objects.get(user=member).id
        owner_id = OrganizationMember.objects.get(user=self.owner).id

        self.assertEqual(
            self.client.delete(f"{members_url}{owner_id}/").status_code, 403
        )
        self.assertEqual(
            client_for(member).delete(f"{members_url}{member_id}/").status_code, 204
        )
        self.assertFalse(OrganizationMember.objects.filter(user=member).exists())

    def test_anonymous_is_rejected(self):
        self.assertEqual(APIClient().get(URL).status_code, 401)
