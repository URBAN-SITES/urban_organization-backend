"""Someone from another organization must not reach anything of this one, on any route."""

import re
from datetime import timedelta

from django.urls import URLResolver, get_resolver
from django.utils import timezone

from core.models import (
    ChatChannel,
    ChatMessage,
    ChecklistItem,
    Comment,
    Label,
    Meeting,
    MeetingRecording,
    Notification,
    OrganizationInvite,
    OrganizationMember,
    ResourceLink,
    SectorMember,
    Team,
    TeamMember,
)
from core.modules.kanban.models.task import Status, Task
from core.modules.kanban.tests.helpers import KanbanTestCase, client_for, make_user
from core.modules.organizations.services.organization import OrganizationService

METHODS = ("get", "post", "put", "patch", "delete")


def api_routes():
    def walk(patterns, prefix=""):
        for entry in patterns:
            if isinstance(entry, URLResolver):
                yield from walk(entry.url_patterns, prefix + str(entry.pattern))
            else:
                yield prefix + str(entry.pattern)

    return [p for p in walk(get_resolver().url_patterns) if p.startswith("api/v1/")]


class CrossTenantTest(KanbanTestCase):
    def setUp(self):
        super().setUp()
        sector_id = self.make_sector()
        self.share_sector(sector_id, self.member)
        task = Task.objects.get(id=self.make_task(sector_id)["id"])
        sector = task.sector
        team = Team.objects.create(owner=self.owner, organization=self.org, name="Core")
        channel = ChatChannel.objects.create(
            organization=self.org, kind="sector", sector=sector
        )
        starts = timezone.now() + timedelta(days=1)
        meeting = Meeting.objects.create(
            sector=sector,
            title="Sync",
            starts_at=starts,
            ends_at=starts + timedelta(hours=1),
        )
        self.ids = {
            "organization_id": self.org.id,
            "slug": self.org.slug,
            "sector_id": sector.id,
            "task_id": task.id,
            "status_id": Status.objects.filter(sector=sector).first().id,
            "team_id": team.id,
            "channel_id": channel.id,
            "message_id": ChatMessage.objects.create(
                channel=channel, author=self.owner
            ).id,
            "comment_id": Comment.objects.create(
                task=task, author=self.owner, content="x"
            ).id,
            "item_id": ChecklistItem.objects.create(task=task, content="x").id,
            "link_id": ResourceLink.objects.create(
                url="https://example.com", created_by=self.owner, task=task
            ).id,
            "label_id": Label.objects.create(sector=sector, name="bug").id,
            "invite_id": OrganizationInvite.objects.create(
                organization=self.org,
                email="guest@a.com",
                token_hash="h" * 64,
                invited_by=self.owner,
            ).id,
            "meeting_id": meeting.id,
            "recording_id": MeetingRecording.objects.create(
                meeting=meeting, egress_id="EG_1", file_key="rec/1.mp4"
            ).id,
            "notification_id": Notification.objects.create(
                user=self.owner, title="Oi"
            ).id,
            "user_id": self.member.id,
        }
        self.members = {
            "teams": TeamMember.objects.create(team=team, user=self.member).id,
            "sectors": SectorMember.objects.get(sector=sector, user=self.member).id,
            "organizations": OrganizationMember.objects.get(
                organization=self.org, user=self.member
            ).id,
        }
        self.outsider = make_user("outsider@b.com")
        OrganizationService.create(self.outsider, name="Other")
        self.outsider_client = client_for(self.outsider)

    def fill(self, route):
        params = re.findall(r"<(?:\w+:)?(\w+)>", route)

        def value(match):
            name = re.match(r"<(?:\w+:)?(\w+)>", match.group(0)).group(1)
            if name == "member_id":
                scope = next(k for k in self.members if f"{k}/" in route)
                return str(self.members[scope])
            return str(self.ids[name])

        if not params or any(p not in self.ids and p != "member_id" for p in params):
            return None
        return "/" + re.sub(r"<[^>]+>", value, route)

    def test_no_route_lets_an_outsider_in(self):
        checked, leaks = 0, []
        for route in api_routes():
            url = self.fill(route)
            if url is None:
                continue
            for method in METHODS:
                res = getattr(self.outsider_client, method)(url, {}, format="json")
                checked += 1
                if 200 <= res.status_code < 300:
                    leaks.append(f"{method.upper()} {url} -> {res.status_code}")
        self.assertGreater(checked, 300)
        self.assertEqual(leaks, [])

    def test_user_list_does_not_show_other_organizations(self):
        res = self.outsider_client.get("/api/v1/users/list/")
        self.assertIn(res.status_code, (200, 403, 404))
        if res.status_code == 200:
            body = res.json()
            rows = body.get("results", body) if isinstance(body, dict) else body
            emails = {row.get("email") for row in rows}
            self.assertNotIn(self.owner.email, emails)
            self.assertNotIn(self.member.email, emails)
