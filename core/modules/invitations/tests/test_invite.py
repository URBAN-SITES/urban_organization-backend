from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.core import mail
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models.user import User
from core.modules.invitations.models.invite import OrganizationInvite
from core.modules.organizations.models.organization import OrganizationMember
from core.modules.organizations.services.organization import OrganizationService

PASSWORD = "x12345678!"


def make_user(email):
    return User.objects.create_user(email=email, password=PASSWORD, name="User")


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@patch("core.modules.invitations.services.invite.FRONTEND_URL", "http://front")
class InviteTests(TestCase):
    def setUp(self):
        self.owner = make_user("owner@a.com")
        self.org = OrganizationService.create(self.owner, name="Acme")
        self.url = f"/api/v1/organizations/{self.org.id}/invitations/"
        self.client = client_for(self.owner)
        self.invitee = make_user("guest@a.com")

    def invite(self, email="guest@a.com", **extra):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.url, {"email": email, **extra})

    def token_from_mail(self):
        link = next(
            line for line in mail.outbox[-1].body.splitlines() if "http" in line
        )
        return parse_qs(urlparse(link.split(": ", 1)[1]).query)["token"][0]

    def test_create_sends_link_and_stores_only_hash(self):
        res = self.invite()
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["status"], "pending")
        self.assertEqual(mail.outbox[0].to, ["guest@a.com"])
        token = self.token_from_mail()
        self.assertNotIn(token, OrganizationInvite.objects.get().token_hash)

    def test_only_admin_invites_and_owner_role_is_rejected(self):
        OrganizationService.add_member(self.owner, self.org.id, "guest@a.com", "member")
        member_client = client_for(self.invitee)
        res = member_client.post(self.url, {"email": "new@a.com"})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(self.invite("new@a.com", role="owner").status_code, 400)

    def test_admin_cannot_invite_another_admin(self):
        admin = make_user("adm@a.com")
        OrganizationService.add_member(self.owner, self.org.id, "adm@a.com", "admin")
        res = client_for(admin).post(self.url, {"email": "x@a.com", "role": "admin"})
        self.assertEqual(res.status_code, 403)

    def test_duplicate_pending_and_existing_member_are_rejected(self):
        self.assertEqual(self.invite().status_code, 201)
        self.assertEqual(self.invite("GUEST@a.com").status_code, 400)
        self.assertEqual(self.invite("owner@a.com").status_code, 400)

    def test_expired_invite_does_not_block_a_new_one(self):
        self.invite()
        OrganizationInvite.objects.update(expires_at=timezone.now() - timedelta(days=1))
        self.assertEqual(self.invite().status_code, 201)
        statuses = sorted(OrganizationInvite.objects.values_list("status", flat=True))
        self.assertEqual(statuses, ["expired", "pending"])

    def test_accept_creates_membership_with_invited_role(self):
        self.invite(role="viewer")
        token = self.token_from_mail()
        res = client_for(self.invitee).post(
            "/api/v1/invitations/accept/", {"token": token}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            OrganizationMember.objects.get(
                user=self.invitee, organization=self.org
            ).role,
            "viewer",
        )
        self.assertEqual(OrganizationInvite.objects.get().status, "accepted")
        # single use
        res = client_for(self.invitee).post(
            "/api/v1/invitations/accept/", {"token": token}
        )
        self.assertEqual(res.status_code, 400)

    def test_accept_is_bound_to_the_invited_e_mail(self):
        self.invite()
        token = self.token_from_mail()
        stranger = client_for(make_user("evil@a.com"))
        res = stranger.post("/api/v1/invitations/accept/", {"token": token})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(OrganizationInvite.objects.get().status, "pending")
        res = stranger.post("/api/v1/invitations/accept/", {"token": "nope"})
        self.assertEqual(res.status_code, 400)

    def test_accept_expired_marks_it_expired(self):
        self.invite()
        token = self.token_from_mail()
        OrganizationInvite.objects.update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        res = client_for(self.invitee).post(
            "/api/v1/invitations/accept/", {"token": token}
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(OrganizationInvite.objects.get().status, "expired")

    def test_revoke_then_accept_fails(self):
        self.invite()
        token = self.token_from_mail()
        invite_id = OrganizationInvite.objects.get().id
        self.assertEqual(self.client.delete(f"{self.url}{invite_id}/").status_code, 204)
        self.assertEqual(self.client.delete(f"{self.url}{invite_id}/").status_code, 400)
        res = client_for(self.invitee).post(
            "/api/v1/invitations/accept/", {"token": token}
        )
        self.assertEqual(res.status_code, 400)

    def test_lists(self):
        self.invite()
        self.assertEqual(len(self.client.get(self.url).json()["results"]), 1)
        mine = client_for(self.invitee).get("/api/v1/invitations/mine/").json()
        self.assertEqual(mine["results"][0]["organization_name"], "Acme")
        outsider = client_for(make_user("out@a.com"))
        self.assertEqual(outsider.get(self.url).status_code, 404)
        self.assertEqual(
            outsider.get("/api/v1/invitations/mine/").json()["results"], []
        )

    def mine_id(self):
        return OrganizationInvite.objects.get().id

    def test_accept_from_my_list_creates_membership_once(self):
        self.invite(role="viewer")
        url = f"/api/v1/invitations/{self.mine_id()}/accept/"
        res = client_for(self.invitee).post(url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["organization_id"], str(self.org.id))
        member = OrganizationMember.objects.get(
            user=self.invitee, organization=self.org
        )
        self.assertEqual(member.role, "viewer")
        self.assertEqual(OrganizationInvite.objects.get().status, "accepted")
        self.assertEqual(client_for(self.invitee).post(url).status_code, 400)
        mine = client_for(self.invitee).get("/api/v1/invitations/mine/").json()
        self.assertEqual(mine["results"], [])

    def test_only_the_invited_e_mail_can_accept_or_decline_by_id(self):
        self.invite()
        stranger = client_for(make_user("evil@a.com"))
        base = f"/api/v1/invitations/{self.mine_id()}"
        self.assertEqual(stranger.post(f"{base}/accept/").status_code, 400)
        self.assertEqual(stranger.post(f"{base}/decline/").status_code, 400)
        self.assertEqual(OrganizationInvite.objects.get().status, "pending")

    def test_decline_closes_the_invitation(self):
        self.invite()
        res = client_for(self.invitee).post(
            f"/api/v1/invitations/{self.mine_id()}/decline/"
        )
        self.assertEqual(res.status_code, 204)
        self.assertEqual(OrganizationInvite.objects.get().status, "revoked")
        self.assertFalse(
            OrganizationMember.objects.filter(
                user=self.invitee, organization=self.org
            ).exists()
        )

    def test_accept_errors_say_what_went_wrong(self):
        self.invite()
        token = self.token_from_mail()
        url = "/api/v1/invitations/accept/"
        stranger = client_for(make_user("evil@a.com")).post(url, {"token": token})
        self.assertEqual(stranger.json()["code"], "invite_wrong_account")
        self.assertEqual(stranger.json()["invited_email"], "g***@a.com")
        unknown = client_for(self.invitee).post(url, {"token": "nope"})
        self.assertEqual(unknown.json()["code"], "invite_invalid")
        self.assertEqual(
            client_for(self.invitee).post(url, {"token": token}).status_code, 200
        )
        again = client_for(self.invitee).post(url, {"token": token})
        self.assertEqual(again.json()["code"], "invite_used")
        self.assertEqual(again.json()["organization_id"], str(self.org.id))

    def test_expired_token_reports_expiry(self):
        self.invite()
        token = self.token_from_mail()
        OrganizationInvite.objects.update(
            expires_at=timezone.now() - timedelta(hours=1)
        )
        res = client_for(self.invitee).post(
            "/api/v1/invitations/accept/", {"token": token}
        )
        self.assertEqual(res.json()["code"], "invite_expired")
        self.assertEqual(OrganizationInvite.objects.get().status, "expired")

    def test_by_id_never_explains_someone_elses_invitation(self):
        self.invite()
        invite_id = OrganizationInvite.objects.get().id
        res = client_for(make_user("evil@a.com")).post(
            f"/api/v1/invitations/{invite_id}/accept/"
        )
        self.assertEqual(res.json()["code"], "invite_invalid")

    def test_preview_tells_whether_the_invited_e_mail_has_an_account(self):
        self.invite()
        token = self.token_from_mail()
        res = APIClient().post("/api/v1/invitations/preview/", {"token": token})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            (
                res.json()["organization_name"],
                res.json()["email"],
                res.json()["has_account"],
            ),
            ("Acme", "guest@a.com", True),
        )
        self.invite("new@a.com")
        newcomer = APIClient().post(
            "/api/v1/invitations/preview/", {"token": self.token_from_mail()}
        )
        self.assertFalse(newcomer.json()["has_account"])
        bad = APIClient().post("/api/v1/invitations/preview/", {"token": "nope"})
        self.assertEqual(bad.json()["code"], "invite_invalid")
