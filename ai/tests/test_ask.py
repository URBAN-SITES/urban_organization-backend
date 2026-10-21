from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from ai.services.ask import AIService


def fake_response(stop_reason="end_turn", text="Paris"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=text),
        ],
    )


@mock.patch("ai.services.ask._client")
class AIServiceTests(SimpleTestCase):
    def test_returns_text_blocks_only(self, client):
        client.return_value.beta.messages.create.return_value = fake_response()
        self.assertEqual(AIService.ask("Capital of France?"), "Paris")

    def test_refusal_becomes_validation_error(self, client):
        client.return_value.beta.messages.create.return_value = fake_response("refusal")
        with self.assertRaises(ValidationError):
            AIService.ask("...")
