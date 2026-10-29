from unittest.mock import patch

from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from core.models.user import User
from core.modules.github.models.github import GitHubConnection, GitHubIdentity
from core.modules.github.tests.helpers import GitHubTestCase

API = "/api/v1/integrations/github/"


class GitHubLoginTests(GitHubTestCase):
    def setUp(self):
        super().setUp()
        self.anonymous = APIClient()

    def login(self, client=None):
        client = client or self.anonymous
        state = self.authorize_state("login", client)
        return client.post(
            f"{API}callback/", {"code": "abc", "state": state}, format="json"
        )

    def test_first_login_creates_account_and_discards_the_token(self):
        self.token_answer()
        self.profile_answer(email="new@example.com")
        res = self.login()
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["purpose"], "login")
        self.assertIn("access_token", res.cookies)
        user = User.objects.get(email="new@example.com")
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.github_identity.login, "octo")
        # login keeps no token: it is revoked on GitHub right away
        self.assertTrue(self.github.called("DELETE", "/applications/Iv1.client/token"))
        self.assertFalse(GitHubConnection.objects.exists())

        # the second login finds the identity even if the e-mail changed on GitHub
        self.profile_answer(email="other@example.com")
        self.assertEqual(self.login(APIClient()).status_code, 200)
        self.assertEqual(User.objects.filter(email="other@example.com").count(), 0)

    def test_login_links_an_existing_account_by_verified_email(self):
        self.token_answer()
        self.profile_answer(email="owner@a.com")
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(GitHubIdentity.objects.get().user, self.owner)
        self.assertTrue(self.owner.has_usable_password())  # e-mail login still works

    def test_login_without_verified_email_is_refused(self):
        self.token_answer()
        self.profile_answer(email=None)
        res = self.login()
        self.assertEqual(res.status_code, 401)
        self.assertFalse(GitHubIdentity.objects.exists())

    def test_tampered_state_and_bad_code(self):
        self.token_answer()
        self.profile_answer()
        res = self.anonymous.post(
            f"{API}callback/", {"code": "abc", "state": "forged"}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        self.github.on(
            "POST", "/login/oauth/access_token", body={"error": "bad_verification_code"}
        )
        self.assertEqual(self.login().status_code, 400)

    def test_link_and_connect_need_a_session(self):
        res = self.anonymous.get(f"{API}authorize/", {"purpose": "connect"})
        self.assertIn(res.status_code, (401, 403))
        # a connect state issued for the owner cannot be redeemed by someone else
        state = self.authorize_state("connect")
        self.token_answer()
        self.profile_answer()
        res = self.member_client.post(
            f"{API}callback/", {"code": "abc", "state": state}, format="json"
        )
        self.assertEqual(res.status_code, 400)

    def test_not_configured(self):
        with patch.dict("os.environ", {"GITHUB_CLIENT_ID": ""}):
            res = self.anonymous.get(f"{API}authorize/", {"purpose": "login"})
            self.assertEqual(res.status_code, 503)
            self.assertEqual(res.json()["code"], "github_not_configured")
            self.assertFalse(self.client.get(API).json()["configured"])


class GitHubLinkTests(GitHubTestCase):
    def test_link_identity_and_refuse_one_taken_by_another_user(self):
        self.token_answer()
        self.profile_answer(id_=99, login="owner-gh")
        state = self.authorize_state("link")
        res = self.client.post(
            f"{API}callback/", {"code": "abc", "state": state}, format="json"
        )
        self.assertEqual(res.json(), {"purpose": "link", "login": "owner-gh"})
        state = self.authorize_state("link", self.member_client)
        res = self.member_client.post(
            f"{API}callback/", {"code": "abc", "state": state}, format="json"
        )
        self.assertEqual(res.status_code, 400)

    def test_unlink_needs_a_password(self):
        GitHubIdentity.objects.create(user=self.owner, github_id=1, login="o")
        self.assertEqual(self.client.delete(f"{API}identity/").status_code, 204)
        self.owner.set_unusable_password()
        self.owner.save()
        GitHubIdentity.objects.create(user=self.owner, github_id=1, login="o")
        self.assertEqual(self.client.delete(f"{API}identity/").status_code, 400)
        self.assertFalse(self.client.get(API).json()["can_unlink"])


class GitHubConnectionTests(GitHubTestCase):
    def test_connect_stores_tokens_encrypted(self):
        self.connect()
        stored = GitHubConnection.objects.get(user=self.owner)
        self.assertEqual(stored.access_token, "ghu_access")
        self.assertIsNotNone(stored.expires_at)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT access_token, refresh_token FROM core_githubconnection"
            )
            raw_access, raw_refresh = cursor.fetchone()
        self.assertNotEqual(raw_access, "ghu_access")
        self.assertNotIn("ghr_refresh", raw_refresh)
        status = self.client.get(API).json()
        self.assertEqual(status["connection"]["login"], "octo")
        self.assertEqual(
            status["install_url"],
            "https://github.com/apps/inceptum-test/installations/new",
        )
        self.assertNotIn("access_token", str(status))

    def test_expired_token_is_refreshed_then_forgotten_when_refresh_fails(self):
        self.connect()
        GitHubConnection.objects.update(expires_at=timezone.now())
        self.token_answer(access="ghu_new", refresh="ghr_new")
        self.installation_answer([])
        self.assertEqual(self.client.get(f"{API}repositories/").status_code, 200)
        self.assertEqual(GitHubConnection.objects.get().access_token, "ghu_new")

        GitHubConnection.objects.update(expires_at=timezone.now())
        self.github.on(
            "POST", "/login/oauth/access_token", body={"error": "bad_refresh_token"}
        )
        res = self.client.get(f"{API}repositories/", {"refresh": "true"})
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["code"], "github_not_connected")
        self.assertFalse(GitHubConnection.objects.exists())

    def test_disconnect_revokes_and_deletes(self):
        self.connect()
        res = self.client.delete(f"{API}connection/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["revoked"])
        call = next(
            kw
            for method, path, kw in self.github.calls
            if path == "/applications/Iv1.client/grant"
        )
        self.assertEqual(call["json"], {"access_token": "ghu_access"})
        self.assertFalse(GitHubConnection.objects.exists())
