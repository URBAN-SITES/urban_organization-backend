"""Repositories: what the user may link, what each project shows and task links."""

from urllib.parse import quote

from django.core.cache import cache
from django.db import IntegrityError
from rest_framework.exceptions import NotFound, ValidationError

from core.models.user import User
from core.modules.github.models.github import ProjectRepository, TaskGitHubLink
from core.modules.github.response_messages import (
    MSG_GITHUB_LINK_EXISTS,
    MSG_GITHUB_REF_NOT_FOUND,
    MSG_GITHUB_REPO_ALREADY_LINKED,
    MSG_GITHUB_REPO_NOT_AUTHORIZED,
)
from core.modules.github.services.client import (
    GitHubForbidden,
    GitHubNotConnected,
    app_settings,
    installation_token,
    paginate,
    request,
)
from core.modules.github.services.oauth import GitHubOAuthService
from core.modules.kanban.services.sector import Role, SectorService
from core.modules.kanban.services.task import TaskService

PAGE_SIZE = 20
REPOS_TTL = 120  # seconds the authorized repository list stays cached per user
ACTIVITY_TTL = 60  # seconds a project's branches/PRs/issues stay cached
RECENT = 10
CHECKED_PULLS = 5  # check runs cost one call per PR


def _repos_key(user_id) -> str:
    return f"github:repos:{user_id}"


def activity_key(github_id) -> str:
    return f"github:activity:{github_id}"


def _with_user_token(user: User, call):
    """Runs `call(token)`; a token GitHub no longer accepts is forgotten."""
    token = GitHubOAuthService.access_token(user)
    try:
        return call(token)
    except GitHubNotConnected:
        GitHubOAuthService.forget(user)
        raise


def _repo_row(repo: dict, installation_id: int) -> dict:
    return {
        "id": repo["id"],
        "name": repo["name"],
        "full_name": repo["full_name"],
        "owner": repo["owner"]["login"],
        "private": repo["private"],
        "language": repo.get("language") or "",
        "description": repo.get("description") or "",
        "html_url": repo["html_url"],
        "default_branch": repo.get("default_branch") or "",
        "pushed_at": repo.get("pushed_at"),
        "installation_id": installation_id,
    }


def check_state(runs: list[dict]) -> str:
    """Summary of a commit's check runs: success, failure, pending or none."""
    if not runs:
        return "none"
    if any(run.get("status") != "completed" for run in runs):
        return "pending"
    bad = {"failure", "timed_out", "cancelled", "action_required", "startup_failure"}
    if any(run.get("conclusion") in bad for run in runs):
        return "failure"
    return "success"


def pull_state(pull: dict) -> str:
    if pull.get("merged_at") or pull.get("merged"):
        return "merged"
    if pull.get("state") == "open" and pull.get("draft"):
        return "draft"
    return pull.get("state", "")


class GitHubRepoService:
    # the user's repositories ---------------------------------------------

    @staticmethod
    def authorized(user: User, fresh: bool = False) -> list[dict]:
        """Every repository the user reaches through an installation of the app."""
        key = _repos_key(user.pk)
        if not fresh and (cached := cache.get(key)) is not None:
            return cached

        def load(token):
            rows = []
            installations = paginate(
                "/user/installations", token=token, key="installations"
            )
            for installation in installations:
                repos = paginate(
                    f"/user/installations/{installation['id']}/repositories",
                    token=token,
                    key="repositories",
                )
                rows += [_repo_row(repo, installation["id"]) for repo in repos]
            return sorted(rows, key=lambda row: row["full_name"].lower())

        rows = _with_user_token(user, load)
        cache.set(key, rows, REPOS_TTL)
        return rows

    @staticmethod
    def search(user: User, filters: dict) -> dict:
        """Server-side search, filters and pagination over the authorized list."""
        rows = GitHubRepoService.authorized(user, fresh=filters.get("refresh", False))
        languages = sorted({row["language"] for row in rows if row["language"]})
        text = filters.get("search", "").strip().lower()
        if text:
            rows = [
                row
                for row in rows
                if text in row["full_name"].lower()
                or text in row["description"].lower()
            ]
        visibility = filters.get("visibility", "all")
        if visibility != "all":
            rows = [row for row in rows if row["private"] == (visibility == "private")]
        if language := filters.get("language"):
            rows = [row for row in rows if row["language"] == language]
        page = filters.get("page", 1)
        start = (page - 1) * PAGE_SIZE
        return {
            "count": len(rows),
            "page": page,
            "page_size": PAGE_SIZE,
            "results": rows[start : start + PAGE_SIZE],
            "languages": languages,
        }

    @staticmethod
    def install_url() -> str:
        slug = app_settings().slug
        return f"https://github.com/apps/{slug}/installations/new" if slug else ""

    # project repositories ------------------------------------------------

    @staticmethod
    def list_for_project(user: User, sector_id):
        sector, _role = SectorService.get_sector(user, sector_id)
        return ProjectRepository.objects.filter(sector=sector)

    @staticmethod
    def link(user: User, sector_id, github_ids: list[int]) -> list[ProjectRepository]:
        """Links one or more repositories the caller can reach; duplicates are refused."""
        sector, _role = SectorService.get_sector(user, sector_id, Role.MANAGER)
        available = {
            row["id"]: row for row in GitHubRepoService.authorized(user, fresh=True)
        }
        missing = [gid for gid in github_ids if gid not in available]
        if missing:
            raise ValidationError({"github_ids": [MSG_GITHUB_REPO_NOT_AUTHORIZED]})
        taken = set(
            ProjectRepository.objects.filter(
                sector=sector, github_id__in=github_ids
            ).values_list("github_id", flat=True)
        )
        if taken or len(set(github_ids)) != len(github_ids):
            raise ValidationError({"github_ids": [MSG_GITHUB_REPO_ALREADY_LINKED]})
        created = []
        try:
            for gid in github_ids:
                row = available[gid]
                created.append(
                    ProjectRepository.objects.create(
                        sector=sector,
                        github_id=gid,
                        installation_id=row["installation_id"],
                        full_name=row["full_name"],
                        private=row["private"],
                        html_url=row["html_url"],
                        default_branch=row["default_branch"],
                        language=row["language"],
                        linked_by=user,
                    )
                )
        except IntegrityError:  # a concurrent request linked it first
            raise ValidationError({"github_ids": [MSG_GITHUB_REPO_ALREADY_LINKED]})
        return created

    @staticmethod
    def unlink(user: User, sector_id, repository_id) -> None:
        """Only removes the association (and its task links); GitHub is untouched."""
        sector, _role = SectorService.get_sector(user, sector_id, Role.MANAGER)
        deleted, _rows = ProjectRepository.objects.filter(
            sector=sector, id=repository_id
        ).delete()
        if not deleted:
            raise NotFound()

    @staticmethod
    def _repository(user: User, repository_id, minimum=Role.VIEWER):
        repository = (
            ProjectRepository.objects.filter(id=repository_id)
            .select_related("sector")
            .first()
        )
        if repository is None:
            raise NotFound()
        SectorService.get_sector(user, repository.sector_id, minimum)
        return repository

    @staticmethod
    def activity(user: User, repository_id) -> dict:
        """Recent branches, pull requests (with checks) and issues, via the installation."""
        repository = GitHubRepoService._repository(user, repository_id)
        key = activity_key(repository.github_id)
        if (cached := cache.get(key)) is not None:
            return cached
        token = installation_token(repository.installation_id)
        base = f"/repositories/{repository.github_id}"

        def get(path, **params):
            response = request(
                "GET", base + path, token=token, user_token=False, params=params
            )
            if response.status_code == 404:
                raise GitHubForbidden()  # the installation lost this repository
            return response

        branches = get("/branches", per_page=RECENT).json()
        pulls = get(
            "/pulls", state="all", sort="updated", direction="desc", per_page=RECENT
        ).json()
        issues = [
            issue
            for issue in get(
                "/issues", state="all", sort="updated", per_page=RECENT * 2
            ).json()
            if "pull_request" not in issue  # the issues API also lists PRs
        ][:RECENT]

        pull_rows = []
        for index, pull in enumerate(pulls):
            checks = None
            if index < CHECKED_PULLS and pull.get("state") == "open":
                runs = get(
                    f"/commits/{pull['head']['sha']}/check-runs", per_page=50
                ).json()
                checks = check_state(runs.get("check_runs", []))
            pull_rows.append(
                {
                    "number": pull["number"],
                    "title": pull["title"],
                    "state": pull_state(pull),
                    "author": (pull.get("user") or {}).get("login", ""),
                    "branch": pull["head"]["ref"],
                    "html_url": pull["html_url"],
                    "updated_at": pull["updated_at"],
                    "checks": checks,
                }
            )
        data = {
            "repository": repository.full_name,
            "branches": [
                {
                    "name": branch["name"],
                    "protected": branch.get("protected", False),
                    "html_url": f"{repository.html_url}/tree/{branch['name']}",
                }
                for branch in branches
            ],
            "pulls": pull_rows,
            "issues": [
                {
                    "number": issue["number"],
                    "title": issue["title"],
                    "state": issue["state"],
                    "author": (issue.get("user") or {}).get("login", ""),
                    "html_url": issue["html_url"],
                    "updated_at": issue["updated_at"],
                    "comments": issue.get("comments", 0),
                }
                for issue in issues
            ],
        }
        cache.set(key, data, ACTIVITY_TTL)
        return data

    # task links -----------------------------------------------------------

    @staticmethod
    def task_links(user: User, task_id):
        task, _sector, _role = TaskService.get_task(user, task_id)
        return TaskGitHubLink.objects.filter(task=task).select_related("repository")

    @staticmethod
    def search_refs(user: User, task_id, text: str) -> list[dict]:
        """Branches and pull requests of the project's repositories matching `text`."""
        task, sector, _role = TaskService.get_task(user, task_id, Role.EDITOR)
        text = text.strip().lower().lstrip("#")
        results = []
        for repository in ProjectRepository.objects.filter(sector=sector):
            token = installation_token(repository.installation_id)
            base = f"/repositories/{repository.github_id}"
            branches = request(
                "GET",
                base + "/branches",
                token=token,
                user_token=False,
                params={"per_page": 100},
            ).json()
            pulls = request(
                "GET",
                base + "/pulls",
                token=token,
                user_token=False,
                params={
                    "state": "all",
                    "sort": "updated",
                    "direction": "desc",
                    "per_page": 50,
                },
            ).json()
            for pull in pulls:
                if text in pull["title"].lower() or text == str(pull["number"]):
                    results.append(
                        {
                            "repository_id": str(repository.id),
                            "repository": repository.full_name,
                            "kind": TaskGitHubLink.Kind.PULL,
                            "ref": str(pull["number"]),
                            "title": pull["title"],
                            "state": pull_state(pull),
                        }
                    )
            for branch in branches:
                if text in branch["name"].lower():
                    results.append(
                        {
                            "repository_id": str(repository.id),
                            "repository": repository.full_name,
                            "kind": TaskGitHubLink.Kind.BRANCH,
                            "ref": branch["name"],
                            "title": branch["name"],
                            "state": "",
                        }
                    )
        return results[:20]

    @staticmethod
    def link_task(
        user: User, task_id, repository_id, kind: str, ref: str
    ) -> TaskGitHubLink:
        task, sector, _role = TaskService.get_task(user, task_id, Role.EDITOR)
        repository = ProjectRepository.objects.filter(
            id=repository_id, sector=sector
        ).first()
        if repository is None:
            raise ValidationError({"repository_id": [MSG_GITHUB_REPO_NOT_AUTHORIZED]})
        if TaskGitHubLink.objects.filter(
            task=task, repository=repository, kind=kind, ref=ref
        ).exists():
            raise ValidationError(MSG_GITHUB_LINK_EXISTS)
        token = installation_token(repository.installation_id)
        base = f"/repositories/{repository.github_id}"
        if kind == TaskGitHubLink.Kind.PULL:
            if not ref.isdigit():
                raise ValidationError(MSG_GITHUB_REF_NOT_FOUND)
            response = request(
                "GET", f"{base}/pulls/{ref}", token=token, user_token=False
            )
        else:
            response = request(
                "GET", f"{base}/branches/{quote(ref)}", token=token, user_token=False
            )
        if response.status_code == 404:
            raise ValidationError(MSG_GITHUB_REF_NOT_FOUND)
        found = response.json()
        if kind == TaskGitHubLink.Kind.PULL:
            title, state, url = found["title"], pull_state(found), found["html_url"]
        else:
            title, state = found["name"], ""
            url = f"{repository.html_url}/tree/{found['name']}"
        try:
            return TaskGitHubLink.objects.create(
                task=task,
                repository=repository,
                kind=kind,
                ref=ref,
                title=title[:500],
                state=state,
                html_url=url,
                created_by=user,
            )
        except IntegrityError:
            raise ValidationError(MSG_GITHUB_LINK_EXISTS)

    @staticmethod
    def unlink_task(user: User, task_id, link_id) -> None:
        task, _sector, _role = TaskService.get_task(user, task_id, Role.EDITOR)
        deleted, _rows = TaskGitHubLink.objects.filter(task=task, id=link_id).delete()
        if not deleted:
            raise NotFound()
