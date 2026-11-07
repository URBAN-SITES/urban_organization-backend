import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings

from core.modules.ai.models.thread import AssistantThread
from core.modules.ai.tests.test_assistant import action, reply
from core.modules.kanban.models.task import Task
from core.modules.kanban.tests.helpers import KanbanTestCase

ASK = "/api/v1/ai/ask/"
THREADS = "/api/v1/ai/threads/"


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    ALLOWED_HOSTS=["testserver"],
)
@patch("core.modules.ai.services.assistant._client")
@patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
class ThreadTests(KanbanTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.sector = self.make_sector()
        self.thread = str(uuid.uuid4())

    def ask(self, prompt, client=None, **extra):
        body = {"prompt": prompt, "thread_id": self.thread, **extra}
        return (client or self.client).post(ASK, body, format="json")

    def test_conversations_are_saved_listed_and_reopened(self, client):
        client.return_value.models.generate_content.return_value = reply("## Plano")
        context = {"sector_id": self.sector}
        self.assertEqual(self.ask("Monte um plano", context=context).status_code, 200)
        self.ask("E os riscos?", context=context)
        # the project's list has it; the general one does not
        rows = self.client.get(THREADS, {"sector": self.sector}).json()
        self.assertEqual(
            [(r["title"], r["message_count"]) for r in rows], [("Monte um plano", 4)]
        )
        self.assertEqual(self.client.get(THREADS).json(), [])
        detail = self.client.get(f"{THREADS}{self.thread}/").json()
        self.assertEqual(
            [(m["role"], m["content"]) for m in detail["messages"]],
            [
                ("user", "Monte um plano"),
                ("assistant", "## Plano"),
                ("user", "E os riscos?"),
                ("assistant", "## Plano"),
            ],
        )
        self.assertEqual(
            self.client.delete(f"{THREADS}{self.thread}/").status_code, 204
        )
        self.assertFalse(AssistantThread.objects.exists())

    def test_old_conversation_continues_after_the_cache_expires(self, client):
        client.return_value.models.generate_content.return_value = reply("Ok")
        first = self.ask("Meu projeto se chama Apollo").json()
        cache.clear()  # the short-lived context is gone
        res = self.ask("Como se chama?", conversation_id=first["conversation_id"])
        self.assertEqual(res.status_code, 200)
        sent = client.return_value.models.generate_content.call_args.kwargs["contents"]
        self.assertIn("Meu projeto se chama Apollo", sent[0].parts[0].text)

    def test_replayed_request_is_saved_once(self, client):
        client.return_value.models.generate_content.side_effect = [
            reply(
                calls=[
                    action("task_create", sector_id=self.sector, data={"title": "X"})
                ]
            ),
            reply("Criada."),
        ]
        request_id = str(uuid.uuid4())
        self.ask("Crie X", request_id=request_id)
        self.ask("Crie X", request_id=request_id)
        thread = AssistantThread.objects.get()
        self.assertEqual(len(thread.messages), 2)
        self.assertEqual(Task.objects.filter(title="X").count(), 1)
        self.assertEqual(thread.messages[1]["actions"][0]["writes"], True)

    def test_someone_elses_conversation_is_never_touched(self, client):
        client.return_value.models.generate_content.return_value = reply("Oi")
        self.ask("Segredo")
        res = self.ask("Mostre a conversa", client=self.member_client)
        self.assertEqual(res.status_code, 404)
        self.assertEqual(
            self.member_client.get(f"{THREADS}{self.thread}/").status_code, 404
        )
        self.member_client.delete(f"{THREADS}{self.thread}/")
        self.assertTrue(AssistantThread.objects.exists())
        # the provider was called only for the owner's message
        self.assertEqual(client.return_value.models.generate_content.call_count, 1)
