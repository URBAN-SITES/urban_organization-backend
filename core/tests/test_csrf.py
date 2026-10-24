from django.test import TestCase


class CsrfEndpointTests(TestCase):
    def test_get_sets_the_csrf_cookie_without_authentication(self):
        res = self.client.get("/api/v1/csrf/")
        self.assertEqual(res.status_code, 204)
        self.assertIn("csrftoken", res.cookies)

    def test_only_get_is_allowed(self):
        self.assertEqual(self.client.post("/api/v1/csrf/").status_code, 405)
