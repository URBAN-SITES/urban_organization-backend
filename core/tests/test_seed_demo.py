from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from core.models import Meeting, Organization, Sector, Task, User


@override_settings(DEBUG=True)
class SeedDemoTests(TestCase):
    def test_creates_full_demo_and_resets(self):
        call_command("seed_demo", stdout=StringIO())
        org = Organization.objects.get(name__startswith="Urban Studio")
        self.assertEqual(org.members.count(), 5)
        self.assertEqual(Sector.objects.filter(organization=org).count(), 5)
        self.assertTrue(
            Task.objects.filter(
                sector__organization=org, completed_at__isnull=False
            ).exists()
        )
        self.assertEqual(Meeting.objects.filter(sector__organization=org).count(), 4)
        self.assertTrue(
            User.objects.get(email="teste@urban.test").check_password(
                "Urban-Teste-2026"
            )
        )

        with self.assertRaises(CommandError):
            call_command("seed_demo")
        call_command("seed_demo", reset=True, stdout=StringIO())
        self.assertEqual(
            Organization.objects.filter(name__startswith="Urban Studio").count(), 1
        )

    @override_settings(DEBUG=False)
    def test_refuses_without_debug(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo")
