from unittest.mock import patch

from django.core import mail
from django.test import SimpleTestCase, TestCase, override_settings

from core.modules.invitations.tasks.invite import send_invite_email_task
from core.tasks.email import send_email_task
from core.utils.email_token_sender import send_email_token, send_email_token_sync

TEST_MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}


@override_settings(MAILERS=TEST_MAILERS)
class EmailTemplateTests(SimpleTestCase):
    def test_code_flows_keep_subject_recipient_and_leading_zero(self):
        for subject, heading in (
            ("Verify your e-mail", "Confirme seu cadastro"),
            ("Your password reset code", "Recupere sua senha"),
            ("Confirm your new e-mail address", "Confirme seu novo e-mail"),
        ):
            with self.subTest(subject=subject):
                send_email_task.run("person@example.invalid", "012345", subject)
                message = mail.outbox[-1]
                self.assertEqual(message.subject, subject)
                self.assertEqual(message.to, ["person@example.invalid"])
                self.assertIn(heading, message.body)
                self.assertIn("012345", message.body)
                self.assertEqual(len(message.alternatives), 1)
                html, mimetype = message.alternatives[0]
                self.assertEqual(mimetype, "text/html")
                self.assertIn(heading, html)
                self.assertIn("012345", html)
                self.assertIn('lang="pt-BR"', html)
                self.assertIn("background-color:#f3f2ef", html)
                self.assertIn("background-color:#0e0e0d", html)
                self.assertIn("color:#ff7a0f", html)
                self.assertNotIn("#2590f6", html)
        self.assertEqual(len(mail.outbox), 3)

    def test_unknown_subject_still_sends_a_code(self):
        send_email_token_sync("person@example.invalid", "123456", "Custom subject")
        message = mail.outbox[0]
        self.assertEqual(message.subject, "Custom subject")
        self.assertIn("Seu código de verificação", message.body)
        self.assertIn("123456", message.alternatives[0].content)

    def test_invitation_preserves_link_and_escapes_html(self):
        organization = 'Pesquisa & Desenvolvimento <script>alert("x")</script>'
        link = "https://example.invalid/invitations/accept?token=abc&source=email"
        send_invite_email_task.run("guest@example.invalid", organization, link)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["guest@example.invalid"])
        self.assertEqual(message.subject, f"You were invited to {organization}")
        self.assertIn(organization, message.body)
        self.assertIn(link, message.body)
        self.assertEqual(len(message.alternatives), 1)
        html, mimetype = message.alternatives[0]
        self.assertEqual(mimetype, "text/html")
        self.assertIn("Aceitar convite", html)
        self.assertIn("Pesquisa &amp; Desenvolvimento &lt;script&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertEqual(html.count(f'href="{link.replace("&", "&amp;")}"'), 2)

    def test_code_is_escaped_in_html(self):
        send_email_token_sync("person@example.invalid", "<b>123</b>", "Custom")
        self.assertIn("&lt;b&gt;123&lt;/b&gt;", mail.outbox[0].alternatives[0].content)

    @patch("core.utils.email_token_sender.EmailMultiAlternatives.send")
    def test_delivery_failure_is_not_silenced(self, send):
        send.side_effect = OSError("SMTP unavailable")
        with self.assertRaises(OSError):
            send_email_token_sync("person@example.invalid", "012345", "Custom")


class EmailSchedulingTests(TestCase):
    @patch("core.tasks.email.send_email_task.delay")
    def test_existing_task_arguments_are_queued_only_after_commit(self, delay):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            send_email_token("person@example.invalid", "012345", "Verify your e-mail")
            delay.assert_not_called()
        self.assertEqual(len(callbacks), 1)
        delay.assert_called_once_with(
            "person@example.invalid", "012345", "Verify your e-mail"
        )

    @patch("core.tasks.email.send_email_task.delay")
    def test_rollback_does_not_queue_delivery(self, delay):
        from django.db import transaction

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            with self.assertRaises(ValueError), transaction.atomic():
                send_email_token(
                    "person@example.invalid", "012345", "Verify your e-mail"
                )
                raise ValueError("Rollback")
        self.assertEqual(callbacks, [])
        delay.assert_not_called()
