import json
import uuid
from datetime import date, timedelta
from unittest.mock import PropertyMock, patch

from django.core.cache import cache
from django.test import override_settings

from core.modules.ai.services.assistant import AssistantService
from core.modules.ai.services.quick_task import draft_task, find_person, quick_create
from core.modules.ai.tests.test_assistant import action, reply
from core.modules.kanban.models.task import Task
from core.modules.kanban.tests.helpers import KanbanTestCase
from rest_framework.exceptions import ValidationError


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    ALLOWED_HOSTS=["testserver"],
)
class QuickTaskTests(KanbanTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.matheus = self.person("matheus@a.com", "Matheus Michalski")
        self.nicole = self.person("nicole@a.com", "Nicole Souza")
        self.sector = self.make_sector()
        for member in (self.matheus, self.nicole):
            self.share_sector(self.sector, member)
        self.tomorrow = date.today() + timedelta(days=1)

    def person(self, email, name):
        user = self.add_org_member(email)
        user.name = name
        user.save()
        return user

    def create(self, **data):
        data.setdefault("title", "Desenvolver fix do frontend")
        return quick_create(self.owner, self.sector, **data)

    def subscriber(self):
        return patch(
            "core.models.user.User.is_subscriber",
            new_callable=PropertyMock,
            return_value=True,
        )

    def draft(self, **data):
        data.setdefault("title", "Desenvolver fix do frontend")
        return draft_task(self.owner, **data)

    def test_the_example_prompt_only_prepares_a_draft(self):
        with patch("core.modules.ai.services.assistant._client") as client:
            client.return_value.models.generate_content.side_effect = [
                reply(
                    calls=[
                        action(
                            "task_draft",
                            data={
                                "title": "Desenvolver fix do frontend",
                                "priority": "high",
                                "due_date": self.tomorrow.isoformat(),
                                "due_time": "12:00",
                                "sector_id": self.sector,
                                "assignees": ["matheus", "nicole"],
                            },
                        )
                    ]
                ),
                reply("Montei o rascunho; ajuste e confirme no cartão."),
            ]
            result = AssistantService.ask(self.owner, "crie uma tarefa para amanhã meio dia")
        receipt = result["actions"][0]
        self.assertEqual((receipt["action"], receipt["status"]), ("task_draft", "succeeded"))
        self.assertFalse(receipt["writes"])
        self.assertFalse(result["unverified"])
        self.assertFalse(Task.objects.filter(title="Desenvolver fix do frontend").exists())
        draft = receipt["result"]
        self.assertEqual([p["name"] for p in draft["assignees"]], ["Matheus Michalski", "Nicole Souza"])
        self.assertEqual((draft["priority"], draft["due_time"]), ("high", "12:00"))
        self.assertEqual(draft["sector"]["id"], self.sector)

    def test_draft_flags_what_is_missing_and_offers_choices(self):
        draft = self.draft()
        self.assertEqual(draft["sector"]["id"], self.sector)  # the only editable sector
        self.assertIn("due_date", draft["missing"])
        self.assertIn("assignees", draft["missing"])
        names = {p["name"] for p in draft["people_options"]}
        self.assertTrue({"Matheus Michalski", "Nicole Souza"} <= names)

    def test_draft_turns_ambiguity_and_missing_access_into_choices(self):
        other = self.person("matheus2@a.com", "Matheus Silva")
        self.share_sector(self.sector, other)
        draft = self.draft(assignees=["matheus", "zeca"])
        reasons = {u["query"]: u for u in draft["unresolved"]}
        self.assertEqual(reasons["matheus"]["reason"], "ambiguous")
        self.assertEqual(len(reasons["matheus"]["candidates"]), 2)
        self.assertEqual(reasons["zeca"]["reason"], "not_found")
        self.assertEqual(draft["assignees"], [])

    def test_draft_without_a_sector_waits_for_the_selector(self):
        self.make_sector(name="Outro")
        draft = self.draft(assignees=["nicole"])
        self.assertIsNone(draft["sector"])
        self.assertEqual(len(draft["sector_options"]), 2)
        self.assertEqual(draft["unresolved"][0]["reason"], "sector_needed")

    def confirm(self, **over):
        body = {
            "request_id": str(uuid.uuid4()),
            "sector_id": self.sector,
            "title": "Desenvolver fix do frontend",
            "priority": "high",
            "due_date": self.tomorrow.isoformat(),
            "due_time": "12:00",
            "assignee_ids": [str(self.matheus.pk), str(self.nicole.pk)],
            **over,
        }
        with self.subscriber():
            return self.client.post("/api/v1/ai/tasks/", body, format="json"), body

    def test_confirming_the_draft_creates_the_task_once(self):
        response, body = self.confirm()
        self.assertEqual(response.status_code, 201, response.content)
        task = Task.objects.get(title="Desenvolver fix do frontend")
        self.assertEqual((task.priority, task.due_date, task.assignee), ("high", self.tomorrow, self.matheus))
        self.assertIn("12:00", task.description)
        self.assertIn("Nicole Souza", task.description)
        self.assertEqual(len(response.json()["notes"]), 2)
        with self.subscriber():
            again = self.client.post("/api/v1/ai/tasks/", body, format="json")
        self.assertEqual(again.status_code, 200)
        self.assertEqual(Task.objects.filter(title="Desenvolver fix do frontend").count(), 1)

    def test_confirming_rejects_people_without_access_and_non_subscribers(self):
        stranger = self.person("stranger@a.com", "Stranger")
        response, _ = self.confirm(assignee_ids=[str(stranger.pk)])
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Task.objects.filter(title="Desenvolver fix do frontend").exists())
        denied = self.client.post("/api/v1/ai/tasks/", {}, format="json")
        self.assertEqual(denied.status_code, 403)

    def test_options_endpoint_lists_assignable_people(self):
        with self.subscriber():
            ok = self.client.get(f"/api/v1/ai/tasks/options/?sector_id={self.sector}")
            bad = self.client.get("/api/v1/ai/tasks/options/")
        self.assertEqual(ok.status_code, 200)
        self.assertIn("Nicole Souza", [p["name"] for p in ok.json()["people"]])
        self.assertEqual(bad.status_code, 400)

    def test_single_person_and_no_time_has_no_notes(self):
        result = self.create(assignees=["nicole"], due_date=self.tomorrow)
        self.assertEqual(result["notes"], [])
        self.assertEqual(Task.objects.get(pk=result["id"]).assignee, self.nicole)

    def test_time_without_date_is_reported(self):
        result = self.create(due_time=__import__("datetime").time(9, 30))
        self.assertIn("sem data", result["notes"][0])

    def test_names_ignore_accents_and_the_word_usuario(self):
        users = [self.nicole, self.matheus]
        self.assertEqual(find_person("usuário NICOLÉ", users), [self.nicole])
        self.assertEqual(find_person("matheus michalski", users), [self.matheus])
        self.assertEqual(find_person("zeca", users), [])

    def test_ambiguous_name_lists_the_candidates(self):
        other = self.person("matheus2@a.com", "Matheus Silva")
        self.share_sector(self.sector, other)
        with self.assertRaises(ValidationError) as error:
            self.create(assignees=["matheus"])
        text = json.dumps(error.exception.detail)
        self.assertIn("Matheus Michalski", text)
        self.assertIn("Matheus Silva", text)
        self.assertFalse(Task.objects.filter(title="Desenvolver fix do frontend").exists())

    def test_unknown_person_creates_nothing(self):
        with self.assertRaises(ValidationError):
            self.create(assignees=["zeca"])
        self.assertFalse(Task.objects.filter(title="Desenvolver fix do frontend").exists())

    def test_person_without_sector_access_is_explained(self):
        unshared = self.make_sector(name="Sem acesso")
        with self.assertRaises(ValidationError) as error:
            quick_create(self.owner, unshared, title="X", assignees=["nicole"])
        self.assertIn("não tem acesso", json.dumps(error.exception.detail, ensure_ascii=False))
