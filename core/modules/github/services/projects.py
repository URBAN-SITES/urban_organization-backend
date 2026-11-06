"""GitHub Projects (v2): list the boards a user can read and import one as a Kanban.

Columns come from the board's "Status" field; each card becomes a task. Importing again
updates the tasks it created before (title, description, column) and adds new cards, so
it never duplicates. Uses the user's GitHub connection token, which needs the GitHub App
"Projects" read permission (see docs/GITHUB.md).
"""

from django.db import transaction
from rest_framework.exceptions import NotFound

from core.models.user import User
from core.modules.github.models.github import GitHubProjectItem
from core.modules.github.response_messages import (
    MSG_GITHUB_PROJECT_NOT_FOUND,
    MSG_GITHUB_PROJECTS_FORBIDDEN,
)
from core.modules.github.services.client import (
    API_URL,
    GitHubForbidden,
    GitHubUnavailable,
    request,
)
from core.modules.github.services.repos import _with_user_token
from core.modules.kanban.models.task import Status
from core.modules.kanban.services.sector import Role, SectorService
from core.modules.kanban.services.status import StatusService
from core.modules.kanban.services.task import TaskService

MAX_ITEMS = 1000

_PROJECT_FIELDS = "id number title url closed"
PROJECTS_QUERY = f"""
query {{
  viewer {{
    login
    projectsV2(first: 50, orderBy: {{field: UPDATED_AT, direction: DESC}}) {{
      nodes {{ {_PROJECT_FIELDS} }}
    }}
    organizations(first: 20) {{
      nodes {{
        login
        projectsV2(first: 50, orderBy: {{field: UPDATED_AT, direction: DESC}}) {{
          nodes {{ {_PROJECT_FIELDS} }}
        }}
      }}
    }}
  }}
}}
"""

ITEMS_QUERY = """
query($id: ID!, $after: String) {
  node(id: $id) {
    ... on ProjectV2 {
      id
      title
      url
      field(name: "Status") {
        ... on ProjectV2SingleSelectField { options { name } }
      }
      items(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          isArchived
          fieldValueByName(name: "Status") {
            ... on ProjectV2ItemFieldSingleSelectValue { name }
          }
          content {
            __typename
            ... on DraftIssue { title body }
            ... on Issue { title body url }
            ... on PullRequest { title body url }
          }
        }
      }
    }
  }
}
"""

# GitHub's default columns land on the ones every project already has
ALIASES = {
    "todo": "a fazer",
    "to do": "a fazer",
    "backlog": "a fazer",
    "in progress": "em andamento",
    "doing": "em andamento",
    "done": "concluído",
}
DONE_NAMES = {"done", "concluído", "concluido", "closed", "feito", "pronto"}
PROGRESS_NAMES = {"in progress", "em andamento", "doing", "fazendo", "in review"}


def _graphql(token: str, query: str, *, partial: bool = False, **variables) -> dict:
    """POST to GitHub GraphQL. With `partial`, data that came with errors is kept
    (an organization that blocks the app must not hide the user's own boards)."""
    response = request(
        "POST",
        f"{API_URL}/graphql",
        token=token,
        json={"query": query, "variables": variables},
    )
    body = response.json()
    errors = body.get("errors") or []
    if errors and not (partial and body.get("data")):
        kinds = {error.get("type") for error in errors}
        if kinds & {"FORBIDDEN", "INSUFFICIENT_SCOPES"}:
            raise GitHubForbidden(MSG_GITHUB_PROJECTS_FORBIDDEN)
        if "NOT_FOUND" in kinds:
            raise NotFound(MSG_GITHUB_PROJECT_NOT_FOUND)
        raise GitHubUnavailable()
    return body.get("data") or {}


def _row(node: dict, owner: str) -> dict:
    return {
        "id": node["id"],
        "number": node["number"],
        "title": node["title"],
        "url": node["url"],
        "closed": node["closed"],
        "owner": owner,
    }


def _category(name: str) -> str:
    key = name.strip().lower()
    if key in DONE_NAMES:
        return Status.Category.DONE
    if key in PROGRESS_NAMES:
        return Status.Category.IN_PROGRESS
    return Status.Category.TODO


class GitHubProjectsService:
    @staticmethod
    def available(user: User) -> list[dict]:
        """Boards of the user and of their organizations, newest first; closed last."""

        def load(token):
            viewer = (_graphql(token, PROJECTS_QUERY, partial=True).get("viewer")) or {}
            rows = [
                _row(node, viewer.get("login", ""))
                for node in ((viewer.get("projectsV2") or {}).get("nodes") or [])
                if node
            ]
            for org in (viewer.get("organizations") or {}).get("nodes") or []:
                if not org:
                    continue
                for node in (org.get("projectsV2") or {}).get("nodes") or []:
                    if node:
                        rows.append(_row(node, org["login"]))
            return sorted(rows, key=lambda row: row["closed"])

        return _with_user_token(user, load)

    @staticmethod
    def _fetch(token: str, project_id: str) -> tuple[dict, list[dict]]:
        items, after = [], None
        while True:
            node = _graphql(token, ITEMS_QUERY, id=project_id, after=after).get("node")
            if not node or "items" not in node:
                raise NotFound(MSG_GITHUB_PROJECT_NOT_FOUND)
            page = node["items"]
            items += page["nodes"]
            if not page["pageInfo"]["hasNextPage"] or len(items) >= MAX_ITEMS:
                return node, items[:MAX_ITEMS]
            after = page["pageInfo"]["endCursor"]

    @staticmethod
    @transaction.atomic
    def import_project(user: User, sector_id, project_id: str) -> dict:
        sector, _role = SectorService.get_sector(user, sector_id, Role.MANAGER)
        board, items = _with_user_token(
            user, lambda token: GitHubProjectsService._fetch(token, project_id)
        )
        statuses = {
            status.name.strip().lower(): status for status in sector.statuses.all()
        }
        result = {
            "project": board["title"],
            "created": 0,
            "updated": 0,
            "columns_created": 0,
            "skipped": 0,
        }

        def column(name: str | None) -> Status:
            if not name:
                return TaskService._default_status(sector)
            key = name.strip().lower()
            found = statuses.get(key) or statuses.get(ALIASES.get(key, ""))
            if found:
                return found
            created = StatusService.create(
                user, sector.pk, name=name.strip()[:100], category=_category(name)
            )
            statuses[key] = created
            result["columns_created"] += 1
            return created

        # the board's columns first, in GitHub's order, even the empty ones
        for option in ((board.get("field") or {}).get("options")) or []:
            column(option["name"])

        known = {
            link.item_id: link
            for link in GitHubProjectItem.objects.filter(sector=sector).select_related(
                "task"
            )
        }
        for item in items:
            content = item.get("content")
            if item.get("isArchived") or not content:
                result["skipped"] += 1
                continue
            title = (content.get("title") or "").strip()[:255] or "Untitled"
            body = content.get("body") or ""
            status = column((item.get("fieldValueByName") or {}).get("name"))
            link = known.get(item["id"])
            if link and link.task.is_active:
                task = link.task
                changes = {
                    field: value
                    for field, value in (("title", title), ("description", body))
                    if getattr(task, field) != value
                }
                moved = task.status_id != status.pk
                if changes:
                    TaskService.update(user, task.pk, changes)
                if moved:
                    TaskService.move(user, task.pk, status, None)
                if changes or moved:
                    result["updated"] += 1
                continue
            task = TaskService.create(
                user, sector.pk, {"title": title, "description": body, "status": status}
            )
            GitHubProjectItem.objects.update_or_create(
                sector=sector,
                item_id=item["id"],
                defaults={
                    "task": task,
                    "project_id": board["id"],
                    "html_url": content.get("url") or board["url"],
                },
            )
            result["created"] += 1
        return result
