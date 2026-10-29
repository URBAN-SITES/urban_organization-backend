"""A fake GitHub: every HTTP call the module makes is answered from a route table."""

import json
from contextlib import ExitStack
from unittest.mock import patch
from urllib.parse import urlparse

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.cache import cache
from django.test import override_settings
from requests.structures import CaseInsensitiveDict

from core.modules.kanban.tests.helpers import KanbanTestCase

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PRIVATE_KEY = _KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()

ENV = {
    "GITHUB_APP_ID": "123",
    "GITHUB_APP_SLUG": "inceptum-test",
    "GITHUB_CLIENT_ID": "Iv1.client",
    "GITHUB_CLIENT_SECRET": "secret",
    "GITHUB_APP_PRIVATE_KEY": PRIVATE_KEY.replace("\n", "\\n"),
    "GITHUB_WEBHOOK_SECRET": "hook-secret",
    "FRONTEND_URL": "http://front.test",
}


def response(status=200, body=None, headers=None) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(body if body is not None else {}).encode()
    result.headers = CaseInsensitiveDict(headers or {})
    return result


class FakeGitHub:
    """routes[(METHOD, path)] = Response or callable(**kwargs) -> Response."""

    def __init__(self):
        self.routes: dict = {}
        self.calls: list = []

    def on(self, method, path, status=200, body=None, headers=None):
        self.routes[(method, path)] = response(status, body, headers)

    def __call__(self, method, url, **kwargs):
        path = urlparse(url).path
        self.calls.append((method, path, kwargs))
        found = self.routes.get((method, path))
        if found is None:
            return response(404, {"message": "Not Found"})
        return found(**kwargs) if callable(found) else found

    def called(self, method, path) -> bool:
        return any(m == method and p == path for m, p, _kw in self.calls)


def repo(id_, full_name, private=False, language="Python"):
    owner, name = full_name.split("/")
    return {
        "id": id_,
        "name": name,
        "full_name": full_name,
        "owner": {"login": owner},
        "private": private,
        "language": language,
        "description": f"{name} repo",
        "html_url": f"https://github.com/{full_name}",
        "default_branch": "main",
        "pushed_at": "2026-10-28T10:00:00Z",
    }


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
class GitHubTestCase(KanbanTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.github = FakeGitHub()
        stack = ExitStack()
        stack.enter_context(patch.dict("os.environ", ENV))
        fake = self.github
        stack.enter_context(patch("requests.request", side_effect=fake))
        stack.enter_context(
            patch(
                "requests.post", side_effect=lambda url, **kw: fake("POST", url, **kw)
            )
        )
        stack.enter_context(
            patch(
                "requests.delete",
                side_effect=lambda url, **kw: fake("DELETE", url, **kw),
            )
        )
        self.addCleanup(stack.close)

    # common GitHub answers -------------------------------------------------

    def token_answer(self, access="ghu_access", refresh="ghr_refresh"):
        self.github.on(
            "POST",
            "/login/oauth/access_token",
            body={
                "access_token": access,
                "refresh_token": refresh,
                "expires_in": 28800,
                "refresh_token_expires_in": 15897600,
                "token_type": "bearer",
            },
        )

    def profile_answer(self, id_=42, login="octo", email="octo@example.com"):
        self.github.on("GET", "/user", body={"id": id_, "login": login, "name": "Octo"})
        emails = [{"email": email, "primary": True, "verified": True}] if email else []
        self.github.on("GET", "/user/emails", body=emails)
        self.github.on("DELETE", "/applications/Iv1.client/token", status=204)
        self.github.on("DELETE", "/applications/Iv1.client/grant", status=204)

    def installation_answer(self, repos, installation_id=7):
        self.github.on(
            "GET",
            "/user/installations",
            body={"total_count": 1, "installations": [{"id": installation_id}]},
        )
        self.github.on(
            "GET",
            f"/user/installations/{installation_id}/repositories",
            body={"total_count": len(repos), "repositories": repos},
        )
        self.github.on(
            "POST",
            f"/app/installations/{installation_id}/access_tokens",
            status=201,
            body={"token": "ghs_installation", "expires_at": "2099-01-01T00:00:00Z"},
        )

    def authorize_state(self, purpose, client=None):
        res = (client or self.client).get(
            "/api/v1/integrations/github/authorize/", {"purpose": purpose}
        )
        self.assertEqual(res.status_code, 200, res.content)
        query = dict(
            part.split("=", 1) for part in urlparse(res.json()["url"]).query.split("&")
        )
        from urllib.parse import unquote

        return unquote(query["state"])

    def connect(self, client=None):
        self.token_answer()
        self.profile_answer()
        state = self.authorize_state("connect", client)
        res = (client or self.client).post(
            "/api/v1/integrations/github/callback/",
            {"code": "abc", "state": state},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        return res
