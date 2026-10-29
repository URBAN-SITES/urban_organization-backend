"""GitHub webhooks: signature check, then refresh what the app shows."""

import hashlib
import hmac

from django.core.cache import cache
from rest_framework.exceptions import PermissionDenied

from core.modules.github.models.github import ProjectRepository, TaskGitHubLink
from core.modules.github.response_messages import MSG_GITHUB_SIGNATURE_INVALID
from core.modules.github.services.client import GitHubNotConfigured, app_settings
from core.modules.github.services.repos import activity_key, pull_state

HANDLED = {
    "pull_request",
    "issues",
    "delete",
    "create",
    "push",
    "check_run",
    "installation",
    "repository",
}


class GitHubWebhookService:
    @staticmethod
    def verify(body: bytes, signature: str) -> None:
        secret = app_settings().webhook_secret
        if not secret:
            raise GitHubNotConfigured()
        expected = (
            "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        )
        if not signature or not hmac.compare_digest(expected, signature):
            raise PermissionDenied(MSG_GITHUB_SIGNATURE_INVALID)

    @staticmethod
    def handle(event: str, payload: dict) -> int:
        """Applies the event; returns how many task links changed."""
        if event not in HANDLED:
            return 0
        if event == "installation" and payload.get("action") == "deleted":
            ids = [repo["id"] for repo in payload.get("repositories") or []]
            for github_id in ids:
                cache.delete(activity_key(github_id))
            return 0
        repo = payload.get("repository") or {}
        github_id = repo.get("id")
        if not github_id:
            return 0
        # every event can change what the project tab shows
        cache.delete(activity_key(github_id))
        if not ProjectRepository.objects.filter(github_id=github_id).exists():
            return 0
        links = TaskGitHubLink.objects.filter(repository__github_id=github_id)
        if event == "pull_request":
            pull = payload["pull_request"]
            return links.filter(
                kind=TaskGitHubLink.Kind.PULL, ref=str(pull["number"])
            ).update(title=pull["title"][:500], state=pull_state(pull))
        if event == "delete" and payload.get("ref_type") == "branch":
            return links.filter(
                kind=TaskGitHubLink.Kind.BRANCH, ref=payload["ref"]
            ).update(state="deleted")
        if event == "create" and payload.get("ref_type") == "branch":
            return links.filter(
                kind=TaskGitHubLink.Kind.BRANCH, ref=payload["ref"]
            ).update(state="")
        if event == "repository" and payload.get("action") == "renamed":
            ProjectRepository.objects.filter(github_id=github_id).update(
                full_name=repo["full_name"], html_url=repo["html_url"]
            )
        return 0
