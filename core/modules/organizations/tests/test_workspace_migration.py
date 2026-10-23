from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class WorkspaceMigrationTests(TransactionTestCase):
    def test_existing_organizations_receive_distinct_addresses(self):
        old = [("core", "0005_chat_sector_mentions_tasks")]
        current = [("core", "0006_workspace_onboarding")]
        try:
            executor = MigrationExecutor(connection)
            executor.migrate(old)
            apps = executor.loader.project_state(old).apps
            User = apps.get_model("core", "User")
            Organization = apps.get_model("core", "Organization")
            user = User.objects.create(email="migration@example.invalid", password="!")
            ids = [
                Organization.objects.create(owner=user, name="Existing").pk
                for _ in range(2)
            ]
            executor = MigrationExecutor(connection)
            executor.migrate(current)
            Organization = executor.loader.project_state(current).apps.get_model(
                "core", "Organization"
            )
            rows = list(Organization.objects.filter(pk__in=ids))
            self.assertEqual(len({row.slug for row in rows}), 2)
            self.assertTrue(all(row.slug and row.name == "Existing" for row in rows))
            self.assertTrue(all(row.team_size == "" for row in rows))
        finally:
            MigrationExecutor(connection).migrate(current)
