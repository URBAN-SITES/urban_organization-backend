from types import SimpleNamespace
from unittest import mock
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from core.modules.ai.services.ask import AINotConfigured, AIService


def fake_response(text="Paris"):
    return SimpleNamespace(text=text)


@mock.patch("core.modules.ai.services.ask._client")
@patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
class AIServiceTests(SimpleTestCase):
    def test_returns_generated_text(self, client):
        client.return_value.models.generate_content.return_value = fake_response(
            "Paris"
        )
        self.assertEqual(AIService.ask("Capital of France?"), "Paris")

    def test_empty_response_becomes_validation_error(self, client):
        client.return_value.models.generate_content.return_value = fake_response("")
        with self.assertRaises(ValidationError):
            AIService.ask("...")

    def test_without_a_key_answers_503_not_500(self, client):
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
            with self.assertRaises(AINotConfigured) as caught:
                AIService.ask("...")
        self.assertEqual(caught.exception.status_code, 503)
        client.assert_not_called()
