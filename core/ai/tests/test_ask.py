from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from core.ai.services.ask import AIService


def fake_response(text="Paris"):
    return SimpleNamespace(text=text)


@mock.patch("core.ai.services.ask._client")
class AIServiceTests(SimpleTestCase):
    def test_returns_generated_text(self, client):
        client.return_value.models.generate_content.return_value = fake_response("Paris")
        self.assertEqual(AIService.ask("Capital of France?"), "Paris")

    def test_empty_response_becomes_validation_error(self, client):
        client.return_value.models.generate_content.return_value = fake_response("")
        with self.assertRaises(ValidationError):
            AIService.ask("...")
