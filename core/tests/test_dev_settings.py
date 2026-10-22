import os
import runpy
from unittest import mock

from django.test import SimpleTestCase


class DevDatabaseSettingsTests(SimpleTestCase):
    def settings_for(self, environment):
        with mock.patch.dict(os.environ, environment, clear=True):
            return runpy.run_module("app.settings.dev")

    def test_defaults_to_sqlite_without_postgres_host(self):
        settings = self.settings_for({})
        self.assertEqual(
            settings["DATABASES"]["default"]["ENGINE"], "django.db.backends.sqlite3"
        )
        self.assertTrue(settings["CELERY_TASK_ALWAYS_EAGER"])

    def test_uses_postgres_environment(self):
        settings = self.settings_for(
            {
                "POSTGRES_HOST": "db",
                "POSTGRES_DB": "resenha",
                "POSTGRES_USER": "developer",
                "POSTGRES_PASSWORD": "test-password",
                "POSTGRES_PORT": "5433",
            }
        )
        self.assertEqual(
            settings["DATABASES"]["default"],
            {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "resenha",
                "USER": "developer",
                "PASSWORD": "test-password",
                "HOST": "db",
                "PORT": "5433",
            },
        )

    def test_postgres_requires_explicit_password(self):
        with self.assertRaises(KeyError):
            self.settings_for({"POSTGRES_HOST": "db"})
