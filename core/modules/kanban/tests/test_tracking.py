import zipfile
from datetime import timedelta
from io import BytesIO

from django.utils import timezone

from core.modules.kanban.models.time_entry import TimeEntry
from core.modules.kanban.tests.helpers import API, KanbanTestCase, client_for, make_user


class TimerTests(KanbanTestCase):
    def test_one_timer_at_a_time(self):
        sector = self.make_sector()
        a, b = self.make_task(sector), self.make_task(sector)
        self.assertIsNone(self.client.get(f"{API}me/timer/").json()["timer"])
        self.client.post(f"{API}tasks/{a['id']}/timer/")
        TimeEntry.objects.filter(task_id=a["id"]).update(
            started_at=timezone.now() - timedelta(minutes=30)
        )
        running = self.client.post(f"{API}tasks/{b['id']}/timer/").json()
        self.assertEqual(running["task_id"], b["id"])
        first = TimeEntry.objects.get(task_id=a["id"])
        self.assertEqual(first.minutes, 30)
        self.assertIsNotNone(first.ended_at)
        stopped = self.client.delete(f"{API}me/timer/").json()["stopped"]
        self.assertEqual(stopped["minutes"], 1)  # at least a minute
        self.assertIsNone(self.client.get(f"{API}me/timer/").json()["timer"])

    def test_manual_time_and_totals(self):
        sector = self.make_sector()
        self.share_sector(sector, self.member, "editor")
        task = self.make_task(sector)
        url = f"{API}tasks/{task['id']}/time/"
        self.client.post(url, {"minutes": 90, "date": "2026-03-02", "note": "revisão"})
        self.member_client.post(url, {"minutes": 30})
        data = self.client.get(url).json()
        self.assertEqual(data["total_minutes"], 120)
        theirs = next(e for e in data["entries"] if e["minutes"] == 30)
        self.assertEqual(
            self.client.delete(f"{API}time/{theirs['id']}/").status_code, 403
        )
        self.assertEqual(
            self.member_client.delete(f"{API}time/{theirs['id']}/").status_code, 204
        )
        self.assertEqual(self.client.post(url, {"minutes": 0}).status_code, 400)

    def test_viewers_cannot_log_time(self):
        sector = self.make_sector()
        self.share_sector(sector, self.member, "viewer")
        task = self.make_task(sector)
        res = self.member_client.post(f"{API}tasks/{task['id']}/timer/")
        self.assertEqual(res.status_code, 403)


class WorkloadTests(KanbanTestCase):
    def test_counts_per_person(self):
        sector = self.make_sector()
        self.share_sector(sector, self.member, "editor")
        today = timezone.localdate()
        self.make_task(
            sector,
            assignee=str(self.member.id),
            estimate=3,
            due_date=(today - timedelta(days=1)).isoformat(),
        )
        self.make_task(
            sector,
            assignee=str(self.member.id),
            estimate=2,
            due_date=(today + timedelta(days=2)).isoformat(),
        )
        self.make_task(sector)
        data = self.client.get(f"{API}sectors/{sector}/workload/").json()
        row = next(p for p in data["people"] if p["user_id"] == str(self.member.id))
        self.assertEqual(
            (row["open"], row["overdue"], row["due_week"], row["points"]), (2, 1, 1, 5)
        )
        self.assertEqual(data["unassigned"], 1)
        # people with nothing open or logged are left out
        self.assertFalse(
            any(p["user_id"] == str(self.owner.id) for p in data["people"])
        )


class ExportTests(KanbanTestCase):
    def test_tasks_sheet_is_a_real_xlsx(self):
        sector = self.make_sector(name="Marketing Digital")
        self.make_task(sector, title="Campanha <verão> & cia", estimate=5)
        res = self.client.get(f"{API}sectors/{sector}/tasks/export/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("md-tarefas.xlsx", res["Content-Disposition"])
        archive = zipfile.ZipFile(BytesIO(res.content))
        sheet = archive.read("xl/worksheets/sheet1.xml").decode()
        self.assertIn("Campanha &lt;verão&gt; &amp; cia", sheet)
        self.assertIn("MD-1", sheet)
        self.assertIn("<v>5</v>", sheet)
        outsider = client_for(make_user("out@a.com"))
        self.assertEqual(
            outsider.get(f"{API}sectors/{sector}/tasks/export/").status_code, 404
        )

    def test_report_pdf(self):
        sector = self.make_sector()
        self.make_task(sector, assignee=str(self.owner.id))
        res = self.client.get(f"{API}organizations/{self.org.id}/reports/pdf/?days=7")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "application/pdf")
        self.assertTrue(res.content.startswith(b"%PDF"))
        bad = self.client.get(f"{API}organizations/{self.org.id}/reports/pdf/?days=5")
        self.assertEqual(bad.status_code, 400)


class HomeWidgetsTests(KanbanTestCase):
    def test_hidden_panels_are_saved(self):
        url = f"{API}users/me/settings/"
        res = self.client.patch(
            url, {"hidden_widgets": ["meetings", "team"]}, format="json"
        )
        self.assertEqual(res.json()["hidden_widgets"], ["meetings", "team"])
        bad = self.client.patch(url, {"hidden_widgets": ["<x>"]}, format="json")
        self.assertEqual(bad.status_code, 400)
