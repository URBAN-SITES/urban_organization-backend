import hashlib
import hmac
import json

from rest_framework.test import APIClient

from core.modules.github.models.github import ProjectRepository, TaskGitHubLink
from core.modules.github.services.repos import check_state
from core.modules.github.tests.helpers import GitHubTestCase, repo
from core.modules.kanban.tests.helpers import API

REPOS = [
    repo(1, "acme/api", private=True, language="Python"),
    repo(2, "acme/web", language="TypeScript"),
    repo(3, "octo/notes", language="Python"),
]


class AuthorizedRepositoryTests(GitHubTestCase):
    def setUp(self):
        super().setUp()
        self.connect()
        self.installation_answer(REPOS)

    def test_search_filters_and_pages(self):
        url = f"{API}integrations/github/repositories/"
        body = self.client.get(url).json()
        self.assertEqual(body["count"], 3)
        self.assertEqual(body["languages"], ["Python", "TypeScript"])
        self.assertEqual(self.client.get(url, {"search": "WEB"}).json()["count"], 1)
        private = self.client.get(url, {"visibility": "private"}).json()["results"]
        self.assertEqual([r["full_name"] for r in private], ["acme/api"])
        python = self.client.get(url, {"language": "Python"}).json()["results"]
        self.assertEqual(len(python), 2)
        self.assertEqual(self.client.get(url, {"page": 2}).json()["results"], [])
        self.assertEqual(
            self.client.get(url, {"visibility": "secret"}).status_code, 400
        )

    def test_rate_limit_and_revoked_token_have_clear_codes(self):
        url = f"{API}integrations/github/repositories/"
        self.github.on(
            "GET",
            "/user/installations",
            status=403,
            headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1900000000"},
        )
        res = self.client.get(url, {"refresh": "true"})
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.json()["code"], "github_rate_limited")
        self.assertTrue(res.json()["reset_at"].startswith("2030-"))

        self.github.on("GET", "/user/installations", status=401)
        res = self.client.get(url, {"refresh": "true"})
        self.assertEqual(res.status_code, 409)
        self.assertEqual(
            self.client.get(f"{API}integrations/github/").json()["connection"], None
        )

    def test_without_connection(self):
        res = APIClient()
        res.force_authenticate(self.member)
        answer = res.get(f"{API}integrations/github/repositories/")
        self.assertEqual(answer.status_code, 409)
        self.assertEqual(answer.json()["code"], "github_not_connected")


class ProjectRepositoryTests(GitHubTestCase):
    def setUp(self):
        super().setUp()
        self.connect()
        self.installation_answer(REPOS)
        self.sector = self.make_sector()
        self.url = f"{API}sectors/{self.sector}/repositories/"

    def link(self, ids, client=None):
        return (client or self.client).post(
            self.url, {"github_ids": ids}, format="json"
        )

    def test_link_many_without_duplicates_and_unlink(self):
        res = self.link([1, 2])
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual([r["full_name"] for r in res.json()], ["acme/api", "acme/web"])
        self.assertEqual(self.link([2]).status_code, 400)  # already linked
        self.assertEqual(self.link([3, 3]).status_code, 400)  # repeated in the request
        self.assertEqual(self.link([999]).status_code, 400)  # not reachable by the user
        linked = self.client.get(self.url).json()
        self.assertEqual(len(linked), 2)

        repository = linked[0]["id"]
        res = self.client.delete(f"{self.url}{repository}/")
        self.assertEqual(res.status_code, 204)
        # unlinking never calls GitHub: no DELETE/PATCH against a repository
        self.assertFalse(
            any(
                m in ("DELETE", "PATCH") and "/repos" in p
                for m, p, _ in self.github.calls
            )
        )
        self.assertEqual(ProjectRepository.objects.count(), 1)

    def test_only_managers_link_and_outsiders_see_nothing(self):
        self.share_sector(self.sector, self.member, "editor")
        self.connect(self.member_client)
        self.assertEqual(self.link([1], self.member_client).status_code, 403)
        self.assertEqual(self.member_client.get(self.url).status_code, 200)
        outsider = self.add_org_member("out@a.com")
        client = APIClient()
        client.force_authenticate(outsider)
        self.assertEqual(client.get(self.url).status_code, 404)

    def test_activity_with_checks_through_the_installation(self):
        repository = self.link([1]).json()[0]["id"]
        base = "/repositories/1"
        self.github.on(
            "GET", f"{base}/branches", body=[{"name": "main", "protected": True}]
        )
        self.github.on(
            "GET",
            f"{base}/pulls",
            body=[
                {
                    "number": 5,
                    "title": "Add login",
                    "state": "open",
                    "draft": False,
                    "merged_at": None,
                    "user": {"login": "octo"},
                    "head": {"ref": "feat/login", "sha": "abc"},
                    "html_url": "https://github.com/acme/api/pull/5",
                    "updated_at": "2026-10-28T10:00:00Z",
                }
            ],
        )
        self.github.on(
            "GET",
            f"{base}/issues",
            body=[
                {
                    "number": 9,
                    "title": "Bug",
                    "state": "open",
                    "html_url": "https://github.com/acme/api/issues/9",
                    "updated_at": "2026-10-28T10:00:00Z",
                    "user": {"login": "ana"},
                },
                {"number": 5, "title": "Add login", "pull_request": {}},
            ],
        )
        self.github.on(
            "GET",
            f"{base}/commits/abc/check-runs",
            body={"check_runs": [{"status": "completed", "conclusion": "failure"}]},
        )
        self.share_sector(self.sector, self.member, "viewer")
        res = self.member_client.get(f"{API}github/repositories/{repository}/activity/")
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        self.assertEqual(data["branches"][0]["name"], "main")
        self.assertEqual(data["pulls"][0]["checks"], "failure")
        self.assertEqual([i["number"] for i in data["issues"]], [9])
        # installation token, not the viewer's own (they never connected GitHub)
        auth = next(
            kw["headers"]["Authorization"]
            for m, p, kw in self.github.calls
            if p == f"{base}/branches"
        )
        self.assertEqual(auth, "Bearer ghs_installation")

    def test_lost_access_to_repository(self):
        repository = self.link([1]).json()[0]["id"]
        res = self.client.get(f"{API}github/repositories/{repository}/activity/")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["code"], "github_forbidden")

    def test_check_summary(self):
        self.assertEqual(check_state([]), "none")
        self.assertEqual(check_state([{"status": "in_progress"}]), "pending")
        done = {"status": "completed", "conclusion": "success"}
        self.assertEqual(
            check_state([done, {**done, "conclusion": "skipped"}]), "success"
        )


class TaskLinkAndWebhookTests(GitHubTestCase):
    def setUp(self):
        super().setUp()
        self.connect()
        self.installation_answer(REPOS)
        self.sector = self.make_sector()
        res = self.client.post(
            f"{API}sectors/{self.sector}/repositories/",
            {"github_ids": [1]},
            format="json",
        )
        self.repository = res.json()[0]["id"]
        self.task = self.make_task(self.sector)["id"]
        self.url = f"{API}tasks/{self.task}/github/"
        self.github.on(
            "GET",
            "/repositories/1/pulls/5",
            body={
                "number": 5,
                "title": "Add login",
                "state": "open",
                "draft": False,
                "merged_at": None,
                "html_url": "https://github.com/acme/api/pull/5",
            },
        )
        self.github.on(
            "GET", "/repositories/1/branches/feat/login", body={"name": "feat/login"}
        )

    def link(self, kind="pull", ref="5", client=None):
        return (client or self.client).post(
            self.url,
            {"repository_id": self.repository, "kind": kind, "ref": ref},
            format="json",
        )

    def test_link_pull_and_branch_once(self):
        res = self.link()
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.json()["state"], "open")
        self.assertEqual(self.link().status_code, 400)
        self.assertEqual(self.link("branch", "feat/login").status_code, 201)
        self.assertEqual(self.link("pull", "77").status_code, 400)  # 404 on GitHub
        self.assertEqual(len(self.client.get(self.url).json()), 2)

    def test_search_and_permissions(self):
        self.github.on("GET", "/repositories/1/branches", body=[{"name": "feat/login"}])
        self.github.on(
            "GET",
            "/repositories/1/pulls",
            body=[{"number": 5, "title": "Add login", "state": "open"}],
        )
        found = self.client.get(f"{self.url}search/", {"q": "login"}).json()
        self.assertEqual(
            {(o["kind"], o["ref"]) for o in found},
            {("pull", "5"), ("branch", "feat/login")},
        )
        self.share_sector(self.sector, self.member, "viewer")
        self.assertEqual(self.link(client=self.member_client).status_code, 403)
        self.assertEqual(self.member_client.get(self.url).status_code, 200)

    def webhook(self, event, payload, secret="hook-secret"):
        body = json.dumps(payload).encode()
        signature = (
            "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        )
        return APIClient().post(
            f"{API}integrations/github/webhook/",
            data=body,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT=event,
            HTTP_X_HUB_SIGNATURE_256=signature,
        )

    def test_webhook_checks_the_signature_and_syncs_pull_state(self):
        self.link()
        self.link("branch", "feat/login")
        payload = {
            "action": "closed",
            "repository": {"id": 1},
            "pull_request": {
                "number": 5,
                "title": "Add login v2",
                "state": "closed",
                "merged": True,
            },
        }
        self.assertEqual(
            self.webhook("pull_request", payload, secret="wrong").status_code, 403
        )
        self.assertEqual(TaskGitHubLink.objects.get(kind="pull").state, "open")
        self.assertEqual(self.webhook("pull_request", payload).status_code, 204)
        pull = TaskGitHubLink.objects.get(kind="pull")
        self.assertEqual((pull.state, pull.title), ("merged", "Add login v2"))

        deleted = {"ref": "feat/login", "ref_type": "branch", "repository": {"id": 1}}
        self.assertEqual(self.webhook("delete", deleted).status_code, 204)
        self.assertEqual(TaskGitHubLink.objects.get(kind="branch").state, "deleted")
        self.assertEqual(self.webhook("ping", {"zen": "hi"}).status_code, 204)
