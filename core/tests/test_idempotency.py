from django.core.cache import cache
from django.http import JsonResponse
from django.test import RequestFactory, SimpleTestCase

from core.middleware.idempotency import IdempotencyMiddleware


class IdempotencyMiddlewareTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.calls = 0

        def view(request):
            self.calls += 1
            return JsonResponse({"call": self.calls}, status=201)

        self.middleware = IdempotencyMiddleware(view)
        self.factory = RequestFactory()

    def post(self, key=None):
        headers = {"Idempotency-Key": key} if key else {}
        return self.middleware(self.factory.post("/api/pay/", headers=headers))

    def test_same_key_replays_first_response(self):
        first, second = self.post("abc"), self.post("abc")
        self.assertEqual(self.calls, 1)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(second.content, first.content)
        self.assertEqual(second["Idempotent-Replayed"], "true")

    def test_without_key_always_runs(self):
        self.post(), self.post()
        self.assertEqual(self.calls, 2)
