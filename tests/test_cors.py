from django.test import TestCase


class CorsTests(TestCase):
    def test_payment_preflight_allows_idempotency_and_csrf_headers(self):
        response = self.client.options(
            "/api/v1/payments/",
            HTTP_ORIGIN="http://localhost:5173",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS=(
                "content-type,idempotency-key,x-csrftoken"
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Access-Control-Allow-Origin"], "http://localhost:5173"
        )
        self.assertEqual(response["Access-Control-Allow-Credentials"], "true")
        allowed_headers = {
            header.strip().lower()
            for header in response["Access-Control-Allow-Headers"].split(",")
        }
        self.assertTrue(
            {"content-type", "idempotency-key", "x-csrftoken"} <= allowed_headers
        )

    def test_allowed_origin_gets_cors_headers_with_credentials(self):
        response = self.client.options(
            "/api/login/",
            HTTP_ORIGIN="http://localhost:5173",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )
        self.assertEqual(
            response["Access-Control-Allow-Origin"], "http://localhost:5173"
        )
        self.assertEqual(response["Access-Control-Allow-Credentials"], "true")

    def test_unknown_origin_gets_no_cors_headers(self):
        response = self.client.get("/api/login/", HTTP_ORIGIN="http://evil.com")
        self.assertNotIn("Access-Control-Allow-Origin", response)
