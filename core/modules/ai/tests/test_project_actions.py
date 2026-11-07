from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings

from core.modules.ai.services.actions import get_action
from core.modules.kanban.models.intake import IntakeRequest
from core.modules.kanban.models.label import Label
from core.modules.kanban.models.page import Page
from core.modules.kanban.tests.helpers import KanbanTestCase, make_user


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
@patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
class ProjectActionTests(KanbanTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.sector = self.make_sector()

    def run_action(self, name, user=None, **arguments):
        return get_action(name).execute(user or self.owner, arguments)

    def test_documents_labels_and_requests(self):
        page = self.run_action(
            "page_create",
            sector_id=self.sector,
            data={"title": "Plano", "content": "## Objetivo"},
        )
        self.assertEqual(Page.objects.get().content, "## Objetivo")
        listed = self.run_action("page_list", sector_id=self.sector)["results"]
        self.assertEqual([p["title"] for p in listed], ["Plano"])
        self.assertNotIn("content", listed[0])  # the list stays light
        self.run_action("page_update", page_id=page["id"], data={"title": "Plano v2"})
        self.assertEqual(Page.objects.get().title, "Plano v2")

        self.run_action("label_create", sector_id=self.sector, data={"name": "Bug"})
        self.assertTrue(Label.objects.filter(name="Bug").exists())

        request = self.run_action(
            "intake_create", sector_id=self.sector, data={"title": "Novo relatório"}
        )
        self.run_action("intake_accept", request_id=request["id"], data={})
        self.assertEqual(
            IntakeRequest.objects.get().state, IntakeRequest.State.ACCEPTED
        )

    def test_meetings_list_and_schedule(self):
        meeting = self.run_action(
            "meeting_create",
            sector_id=self.sector,
            data={
                "title": "Daily",
                "starts_at": "2030-01-01T10:00:00-03:00",
                "ends_at": "2030-01-01T10:30:00-03:00",
            },
        )
        self.assertEqual(meeting["title"], "Daily")
        rows = self.run_action(
            "meeting_list", sector_id=self.sector, data={"when": "upcoming"}
        )["results"]
        self.assertEqual([m["title"] for m in rows], ["Daily"])

    def test_permissions_still_apply(self):
        outsider = make_user("fora@a.com")
        with self.assertRaises(Exception):
            self.run_action(
                "page_create", user=outsider, sector_id=self.sector, data={"title": "X"}
            )
