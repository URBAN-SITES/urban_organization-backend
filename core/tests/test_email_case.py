from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from core.models.email_verification import EmailVerification
from core.models.user import User
from core.services.registration import RegistrationService

API = "/api/v1/"
GOOGLE = "core.services.google_auth.id_token.verify_oauth2_token"
SEND = "core.services.registration.send_email_token"


class EmailCaseTests(TestCase):
    def setUp(self):
        cache.clear()  # the login throttle (10/min) is shared by every test
        self.addCleanup(cache.clear)

    def test_registration_stores_lowercase_and_reuses_the_pending_user(self):
        with mock.patch(SEND):
            RegistrationService.request_registration("Foo@Example.com")
            RegistrationService.request_registration("foo@example.COM")
        self.assertEqual(
            list(User.objects.values_list("email", flat=True)), ["foo@example.com"]
        )

    def test_registration_can_be_confirmed_with_another_case(self):
        with mock.patch(SEND):
            RegistrationService.request_registration("Foo@Example.com")
        verification = EmailVerification.objects.get(user__email="foo@example.com")
        verification.set_code("123456")
        verification.save()

        RegistrationService.confirm_registration(
            "FOO@example.com", "123456", "Foo", "S3cure-pass!"
        )

        user = User.objects.get(email="foo@example.com")
        self.assertTrue(user.is_active)
        self.assertEqual(User.objects.count(), 1)

    def test_login_ignores_case_for_new_and_legacy_accounts(self):
        User.objects.create_user("new@a.com", "S3cure-pass!", name="N")
        # created before e-mails were lowercased
        User.objects.create(email="Legacy@A.com", name="L", password="x")
        legacy = User.objects.get(email="Legacy@A.com")
        legacy.set_password("S3cure-pass!")
        legacy.save()

        for typed in ("NEW@a.com", "New@A.com", "legacy@a.com", "LEGACY@A.COM"):
            res = self.client.post(
                f"{API}login/", {"email": typed, "password": "S3cure-pass!"}
            )
            self.assertEqual(res.status_code, 200, typed)

    def test_login_with_a_wrong_password_still_fails(self):
        User.objects.create_user("new@a.com", "S3cure-pass!", name="N")
        res = self.client.post(f"{API}login/", {"email": "NEW@a.com", "password": "no"})
        self.assertEqual(res.status_code, 403)

    def test_find_by_email_prefers_exact_and_refuses_ambiguity(self):
        upper = User.objects.create(email="Dup@a.com", name="U", password="x")
        lower = User.objects.create(email="dup@a.com", name="L", password="x")
        self.assertEqual(User.objects.find_by_email("dup@a.com"), lower)
        self.assertEqual(User.objects.find_by_email("Dup@a.com"), upper)
        self.assertIsNone(User.objects.find_by_email("DUP@a.com"))

    @mock.patch(GOOGLE)
    def test_google_login_matches_an_existing_account_in_any_case(self, verify):
        legacy = User.objects.create_user("g@gmail.com", "x", name="G")
        verify.return_value = {
            "email": "G@Gmail.com",
            "email_verified": True,
            "name": "G",
        }

        res = self.client.post(f"{API}login/google/", {"credential": "token"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(User.objects.get().pk, legacy.pk)

    @mock.patch(GOOGLE)
    def test_google_login_stores_new_accounts_in_lowercase(self, verify):
        verify.return_value = {
            "email": "New@Gmail.com",
            "email_verified": True,
            "name": "N",
        }
        self.client.post(f"{API}login/google/", {"credential": "token"})
        self.assertEqual(User.objects.get().email, "new@gmail.com")

    def test_email_change_rejects_another_users_address_in_any_case(self):
        User.objects.create_user("taken@a.com", "x", name="T")
        me = User.objects.create_user("me@a.com", "S3cure-pass!", name="M")
        self.client.force_login(me)
        with mock.patch("core.services.email_change.send_email_token"):
            from core.services.email_change import EmailChangeService

            with self.assertRaises(Exception):
                EmailChangeService.request_change(me, "TAKEN@a.com")
            # changing only the case of your own address is allowed
            EmailChangeService.request_change(me, "ME@a.com")
