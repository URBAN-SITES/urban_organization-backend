from datetime import timedelta

from django.utils import timezone

from core.modules.kanban.tests.helpers import API, KanbanTestCase


class DashboardTests(KanbanTestCase):
    def dashboard(self, client=None):
        res = (client or self.client).get(f"{API}organizations/{self.org.id}/dashboard/")
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()

    def test_counts_my_open_overdue_and_done_tasks(self):
        sector = self.make_sector()
        statuses = self.status_ids(sector)
        today = timezone.localdate()
        late = self.make_task(
            sector,
            title="Late",
            assignee=str(self.owner.id),
            due_date=str(today - timedelta(days=2)),
        )
        self.make_task(sector, title="Today", assignee=str(self.owner.id), due_date=str(today))
        finished = self.make_task(sector, title="Finished", assignee=str(self.owner.id))
        res = self.client.post(
            f"{API}tasks/{finished['id']}/move/", {"status": statuses["Done"]}
        )
        self.assertEqual(res.status_code, 200, res.content)

        data = self.dashboard()
        self.assertEqual(data["open_tasks"], 2)
        self.assertEqual(data["overdue"], 1)
        self.assertEqual(data["overdue_title"], "Late")
        self.assertEqual(data["done_this_week"], 1)
        self.assertEqual([t["id"] for t in data["today"]][0], late["id"])
        self.assertTrue(data["today"][0]["is_overdue"])
        self.assertEqual(data["weekly_done"][-1]["done"], 1)
        self.assertEqual(data["open_by_sector"], [{"sector": "Board", "open": 2}])
        self.assertEqual(data["activity"][0]["kind"], "done")

    def test_private_sector_is_hidden_from_non_participants(self):
        sector = self.make_sector()
        self.make_task(sector, title="Secret", assignee=str(self.owner.id))
        data = self.dashboard(self.member_client)
        self.assertEqual(data["open_tasks"], 0)
        self.assertEqual(data["open_by_sector"], [])

    def test_requires_organization_membership(self):
        from core.modules.kanban.tests.helpers import client_for, make_user

        res = client_for(make_user("out@a.com")).get(
            f"{API}organizations/{self.org.id}/dashboard/"
        )
        self.assertIn(res.status_code, (403, 404))
