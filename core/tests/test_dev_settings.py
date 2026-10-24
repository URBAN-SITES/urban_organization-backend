import os
import runpy
from unittest import mock

from django.test import SimpleTestCase


class DevDatabaseSettingsTests(SimpleTestCase):
    def settings_for(self, environment):
        with mock.patch.dict(os.environ, environment, clear=True):
            return runpy.run_module("app.settings.dev")

    def settings_for_prod(self, environment):
        with mock.patch.dict(os.environ, environment, clear=True):
            return runpy.run_module("app.settings.prod")

    def test_defaults_to_sqlite_without_postgres_host(self):
        settings = self.settings_for({})
        self.assertEqual(
            settings["DATABASES"]["default"]["ENGINE"], "django.db.backends.sqlite3"
        )
        self.assertTrue(settings["CELERY_TASK_ALWAYS_EAGER"])

    @mock.patch("os.path.exists", return_value=False)
    def test_ignores_container_db_host_when_not_in_docker(self, _mock_exists):
        settings = self.settings_for(
            {
                "POSTGRES_HOST": "db",
                "POSTGRES_PASSWORD": "test-password",
            }
        )
        self.assertEqual(
            settings["DATABASES"]["default"]["ENGINE"], "django.db.backends.sqlite3"
        )

    @mock.patch("os.path.exists", return_value=False)
    def test_prod_uses_localhost_when_db_service_is_not_available(self, _mock_exists):
        settings = self.settings_for_prod(
            {
                "SECRET_KEY": "test-secret",
                "POSTGRES_HOST": "db",
                "POSTGRES_DB": "resenha",
                "POSTGRES_USER": "developer",
                "POSTGRES_PASSWORD": "test-password",
                "POSTGRES_PORT": "5433",
            }
        )
        self.assertEqual(settings["DATABASES"]["default"]["HOST"], "localhost")

    @mock.patch("os.path.exists", return_value=True)
    def test_uses_postgres_environment(self, _mock_exists):
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

    @mock.patch("os.path.exists", return_value=True)
    def test_postgres_requires_explicit_password(self, _mock_exists):
        with self.assertRaises(KeyError):
            self.settings_for({"POSTGRES_HOST": "db"})
