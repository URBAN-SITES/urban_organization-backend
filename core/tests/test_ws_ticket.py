from unittest import mock

from asgiref.sync import async_to_sync
from django.core import signing
from django.core.cache import cache
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from core.models import User
from core.websockets.auth import create_ticket, get_user_from_ticket


class WebSocketTicketTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email="ws@example.test", password="Senha-de-teste-123", name="WS"
        )

    def resolve(self, ticket):
        return async_to_sync(get_user_from_ticket)(ticket)

    def test_endpoint_requires_login(self):
        self.assertIn(APIClient().post("/api/v1/ws-ticket/").status_code, (401, 403))

    def test_endpoint_returns_a_ticket_for_the_logged_user(self):
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.post("/api/v1/ws-ticket/")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.resolve(response.data["ticket"]).pk, self.user.pk)

    def test_ticket_works_only_once(self):
        ticket = create_ticket(self.user)
        self.assertTrue(self.resolve(ticket).is_authenticated)
        self.assertFalse(self.resolve(ticket).is_authenticated)

    def test_tampered_or_foreign_tickets_are_rejected(self):
        self.assertFalse(self.resolve(create_ticket(self.user) + "x").is_authenticated)
        other_salt = signing.dumps(str(self.user.pk), salt="other")
        self.assertFalse(self.resolve(other_salt).is_authenticated)

    def test_expired_ticket_is_rejected(self):
        ticket = create_ticket(self.user)
        with mock.patch("core.websockets.auth.TICKET_MAX_AGE", -1):
            self.assertFalse(self.resolve(ticket).is_authenticated)

    def test_inactive_user_is_rejected(self):
        ticket = create_ticket(self.user)
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertFalse(self.resolve(ticket).is_authenticated)
