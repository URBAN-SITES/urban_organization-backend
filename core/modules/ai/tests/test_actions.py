import json
import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings
from rest_framework.exceptions import (
    APIException,
    NotFound,
    PermissionDenied,
    ValidationError,
)

from core.modules.ai.services.actions import get_action, registry
from core.modules.kanban.models.task import Task
from core.modules.kanban.tests.helpers import KanbanTestCase
from core.modules.organizations.models.organization import OrganizationMember


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ActionTests(KanbanTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.sector = self.make_sector()

    def execute(self, name, data=None, user=None, **ids):
        arguments = {key: str(value) for key, value in ids.items()}
        if data is not None:
            arguments["data"] = data
        return get_action(name).execute(user or self.owner, arguments)

    def test_create_move_update_and_delete_task_with_subtask(self):
        task = self.execute(
            "task_create",
            {"title": "Launch", "due_date": "2026-11-01"},
            sector_id=self.sector,
        )
        child = self.execute(
            "task_create",
            {"title": "Review", "parent": task["id"]},
            sector_id=self.sector,
        )
        updated = self.execute(
            "task_update", {"title": "Launch v2"}, task_id=task["id"]
        )
        self.assertEqual(updated["title"], "Launch v2")
        statuses = self.execute("status_list", sector_id=self.sector)["results"]
        done = next(row for row in statuses if row["category"] == "done")
        moved = self.execute("task_move", {"status": done["id"]}, task_id=task["id"])
        self.assertIsNotNone(moved["completed_at"])
        self.execute("task_delete", task_id=task["id"])
        self.assertFalse(Task.objects.get(pk=task["id"]).is_active)
        self.assertFalse(Task.objects.get(pk=child["id"]).is_active)

    def test_organization_sector_team_columns_and_members(self):
        org = self.execute("organization_create", {"name": "New workspace"})
        self.assertEqual(
            self.execute("organization_get", organization_id=org["id"])["current_role"],
            "owner",
        )
        team = self.execute(
            "team_create", {"name": "Engineering"}, organization_id=self.org.pk
        )
        sector = self.execute(
            "sector_create", {"name": "Roadmap"}, organization_id=self.org.pk
        )
        member = self.execute(
            "team_member_add",
            {"user_id": str(self.member.pk)},
            organization_id=self.org.pk,
            team_id=team["id"],
        )
        self.execute(
            "team_member_role",
            {"role": "lead"},
            organization_id=self.org.pk,
            team_id=team["id"],
            member_id=member["id"],
        )
        link = self.execute(
            "sector_team_add", {"team_id": team["id"]}, sector_id=sector["id"]
        )
        self.assertEqual(
            self.execute("sector_get", user=self.member, sector_id=sector["id"])["id"],
            sector["id"],
        )
        column = self.execute(
            "status_create",
            {"name": "Review", "category": "in_progress"},
            sector_id=sector["id"],
        )
        self.execute(
            "status_update",
            {"name": "QA"},
            sector_id=sector["id"],
            status_id=column["id"],
        )
        self.execute("status_delete", sector_id=sector["id"], status_id=column["id"])
        self.execute("sector_team_remove", sector_id=sector["id"], link_id=link["id"])
        self.execute(
            "team_member_remove",
            organization_id=self.org.pk,
            team_id=team["id"],
            member_id=member["id"],
        )
        self.execute("team_delete", organization_id=self.org.pk, team_id=team["id"])
        self.execute("sector_update", {"name": "Roadmap v2"}, sector_id=sector["id"])
        self.execute("sector_delete", sector_id=sector["id"])
        self.execute(
            "organization_update", {"name": "Renamed"}, organization_id=org["id"]
        )
        self.execute("organization_delete", organization_id=org["id"])

    def test_invitation_creation_with_sector_and_revocation(self):
        invite = self.execute(
            "invitation_create",
            {"email": "invitee@example.com", "sector_ids": [self.sector]},
            organization_id=self.org.pk,
        )
        self.assertEqual(invite["email"], "invitee@example.com")
        self.assertEqual(invite["sector_ids"], [self.sector])
        self.assertNotIn("token", invite)
        self.execute(
            "invitation_revoke", organization_id=self.org.pk, invite_id=invite["id"]
        )
        listed = self.execute("invitation_list", organization_id=self.org.pk)["results"]
        self.assertTrue(all(row["status"] != "pending" for row in listed))

    def test_private_sector_and_cross_organization_are_protected(self):
        for action, data in (("task_list", None), ("task_create", {"title": "Denied"})):
            with self.subTest(action=action), self.assertRaises(NotFound):
                self.execute(action, data, user=self.member, sector_id=self.sector)
        outsider = self.add_org_member("outsider@example.com")
        OrganizationMember.objects.filter(user=outsider, organization=self.org).delete()
        with self.assertRaises(NotFound):
            self.execute("organization_get", user=outsider, organization_id=self.org.pk)

    def test_viewer_cannot_write_and_editor_cannot_manage_sector(self):
        self.share_sector(self.sector, self.member, "viewer")
        with self.assertRaises(PermissionDenied):
            self.execute(
                "task_create",
                {"title": "Denied"},
                user=self.member,
                sector_id=self.sector,
            )
        task = self.execute("task_create", {"title": "Private"}, sector_id=self.sector)
        with self.assertRaises(PermissionDenied):
            self.execute("task_delete", user=self.member, task_id=task["id"])
        with self.assertRaises(PermissionDenied):
            self.execute(
                "invitation_create",
                {"email": "x@example.com"},
                user=self.member,
                organization_id=self.org.pk,
            )

    def test_invalid_relationship_and_actor_spoofing_are_rejected(self):
        other_sector = self.make_sector(name="Other")
        statuses = self.execute("status_list", sector_id=other_sector)["results"]
        with self.assertRaises(ValidationError):
            self.execute(
                "task_create",
                {"title": "Bad", "status": statuses[0]["id"]},
                sector_id=self.sector,
            )
        for field in ("owner", "user", "is_subscriber", "is_active"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.execute(
                    "task_create",
                    {"title": "Bad", field: str(self.owner.pk)},
                    sector_id=self.sector,
                )
        with self.assertRaises(ValidationError):
            get_action("task_list").execute(
                self.owner, {"sector_id": self.sector, "user_id": str(self.member.pk)}
            )

    def test_checklists_comments_links_and_agenda(self):
        task = self.execute(
            "task_create",
            {"title": "Delivery", "due_date": "2026-11-02"},
            sector_id=self.sector,
        )
        item = self.execute(
            "checklist_create", {"content": "Check"}, task_id=task["id"]
        )
        done = self.execute(
            "checklist_update",
            {"is_done": True},
            task_id=task["id"],
            item_id=item["id"],
        )
        self.assertTrue(done["is_done"])
        comment = self.execute(
            "comment_create", {"content": "Ready"}, task_id=task["id"]
        )
        self.execute(
            "comment_update",
            {"content": "Reviewed"},
            task_id=task["id"],
            comment_id=comment["id"],
        )
        link = self.execute(
            "link_task_create",
            {"title": "Docs", "url": "https://example.com"},
            task_id=task["id"],
        )
        self.assertEqual(
            self.execute("link_task_list", task_id=task["id"])["results"][0]["id"],
            link["id"],
        )
        agenda = self.execute(
            "agenda_deliveries",
            {"start": "2026-11-01", "end": "2026-11-30"},
            organization_id=self.org.pk,
        )
        self.assertEqual(agenda["results"][0]["id"], task["id"])
        self.execute("link_delete", link_id=link["id"])
        self.execute("comment_delete", task_id=task["id"], comment_id=comment["id"])
        self.execute("checklist_delete", task_id=task["id"], item_id=item["id"])

    def test_pagination_and_preferences(self):
        for index in range(3):
            self.execute(
                "task_create", {"title": f"Task {index}"}, sector_id=self.sector
            )
        action = get_action("task_list")
        first = action.execute(
            self.owner, {"sector_id": self.sector, "page": {"limit": 2}}
        )
        second = action.execute(
            self.owner,
            {
                "sector_id": self.sector,
                "page": {"limit": 2, "offset": first["next_offset"]},
            },
        )
        self.assertEqual(len(first["results"]) + len(second["results"]), 3)
        self.assertIsNone(second["next_offset"])
        settings = self.execute("preferences_update", {"timezone": "America/Sao_Paulo"})
        self.assertEqual(settings["timezone"], "America/Sao_Paulo")

    def test_catalog_has_no_payment_or_arbitrary_execution_capability(self):
        catalog = registry()
        self.assertGreater(len(catalog), 60)
        for name in (
            "payment_list",
            "payment_create",
            "payment_refund",
            "execute_sql",
            "http_request",
            "__import__",
        ):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                get_action(name)
        encoded = json.dumps([a.describe() for a in catalog.values()])
        self.assertNotIn("access_token", encoded)
        self.assertNotIn("is_subscriber", encoded)

    @patch(
        "core.modules.ai.services.actions.GoogleCalendarService.create_meet",
        return_value="https://meet.google.com/abc-defg-hij",
    )
    def test_chat_and_meet_use_channel_permissions(self, meet):
        channels = self.execute("chat_channels", organization_id=self.org.pk)["results"]
        channel_id = channels[0]["id"]
        message = self.execute("chat_send", {"content": "Hello"}, channel_id=channel_id)
        self.execute("chat_edit", {"content": "Updated"}, message_id=message["id"])
        result = self.execute("meet_start", channel_id=channel_id)
        self.assertTrue(result["posted"])
        meet.assert_called_once()
        with self.assertRaises(NotFound):
            self.execute("meet_start", channel_id=uuid.uuid4())
        meet.assert_called_once()
        self.execute("chat_delete", message_id=message["id"])

    @patch(
        "core.modules.ai.services.actions.GoogleCalendarService.create_meet",
        return_value="https://meet.google.com/abc-defg-hij",
    )
    @patch(
        "core.modules.ai.services.actions.ChatService.send", side_effect=APIException()
    )
    def test_meet_keeps_created_link_if_chat_post_fails(self, send, meet):
        channel = self.execute("chat_channels", organization_id=self.org.pk)["results"][
            0
        ]
        result = self.execute("meet_start", channel_id=channel["id"])
        self.assertFalse(result["posted"])
        self.assertEqual(result["url"], meet.return_value)
