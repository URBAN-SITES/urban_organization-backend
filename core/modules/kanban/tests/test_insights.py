from datetime import timedelta

from django.utils import timezone

from core.modules.kanban.tests.helpers import API, KanbanTestCase, client_for, make_user


class InsightsTestCase(KanbanTestCase):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.sector = self.make_sector()
        self.statuses = self.status_ids(self.sector)

    def url(self, name):
        return f"{API}organizations/{self.org.id}/{name}/"

    def task(self, title, days=None, done=False, **extra):
        due = (
            {"due_date": str(self.today + timedelta(days=days))}
            if days is not None
            else {}
        )
        task = self.make_task(
            self.sector, title=title, assignee=str(self.owner.id), **due, **extra
        )
        if done:
            res = self.client.post(
                f"{API}tasks/{task['id']}/move/", {"status": self.statuses["Concluído"]}
            )
            self.assertEqual(res.status_code, 200, res.content)
        return task


class CalendarTests(InsightsTestCase):
    def get(self, start, end, client=None):
        return (client or self.client).get(
            self.url("calendar"), {"start": str(start), "end": str(end)}
        )

    def test_lists_deliveries_in_range_with_a_state_each(self):
        self.task("Late", days=-3)
        self.task("Soon", days=2)
        self.task("Finished", days=1, done=True)
        self.task("Far away", days=40)
        self.task("No date")

        res = self.get(self.today - timedelta(days=5), self.today + timedelta(days=10))

        self.assertEqual(res.status_code, 200, res.content)
        states = {t["title"]: t["state"] for t in res.json()}
        self.assertEqual(states, {"Late": "late", "Soon": "todo", "Finished": "done"})
        self.assertEqual([t["title"] for t in res.json()][0], "Late")  # ordered by date

    def test_hidden_from_people_without_access_to_the_sector(self):
        self.task("Secret", days=1)
        res = self.get(self.today, self.today + timedelta(days=3), self.member_client)
        self.assertEqual(res.json(), [])

    def test_range_must_be_valid_and_short(self):
        self.assertEqual(
            self.get(self.today, self.today - timedelta(days=1)).status_code, 400
        )
        self.assertEqual(
            self.get(self.today, self.today + timedelta(days=63)).status_code, 400
        )
        self.assertEqual(self.client.get(self.url("calendar")).status_code, 400)

    def test_non_members_cannot_read_it(self):
        outsider = client_for(make_user("out@a.com"))
        self.assertEqual(
            self.get(self.today, self.today + timedelta(days=1), outsider).status_code,
            404,
        )


class ReportTests(InsightsTestCase):
    def test_counts_deliveries_time_and_punctuality(self):
        self.task("On time", days=2, done=True)
        self.task("Late delivery", days=-2, done=True)
        self.task("Open late", days=-1)
        self.task("Open", days=4)

        data = self.client.get(self.url("reports")).json()

        self.assertEqual(data["days"], 30)
        self.assertEqual(data["completed"], 2)
        self.assertEqual(data["on_time_pct"], 50)
        self.assertEqual(data["open"], 2)
        self.assertEqual(data["overdue"], 1)
        self.assertEqual(data["overdue_by_sector"], [{"sector": "Board", "overdue": 1}])
        self.assertEqual(data["weekly_done"][-1]["done"], 2)
        self.assertIsNotNone(data["avg_days_to_complete"])

    def test_people_table(self):
        self.task("A", days=2, done=True)
        self.task("B", days=-1)
        (person,) = self.client.get(self.url("reports")).json()["people"]
        self.assertEqual(
            (person["name"], person["completed"], person["open"], person["overdue"]),
            ("User", 1, 1, 1),
        )
        self.assertEqual(person["on_time_pct"], 100)

    def test_empty_organization_has_no_percentages(self):
        data = self.client.get(self.url("reports")).json()
        self.assertEqual(
            (data["completed"], data["on_time_pct"], data["people"]), (0, None, [])
        )

    def test_period_is_one_of_7_30_90(self):
        self.assertEqual(
            self.client.get(self.url("reports"), {"days": 7}).json()["days"], 7
        )
        self.assertEqual(
            self.client.get(self.url("reports"), {"days": 5}).status_code, 400
        )

    def test_private_sector_numbers_stay_private(self):
        self.task("Secret", days=-1)
        data = self.member_client.get(self.url("reports")).json()
        self.assertEqual((data["open"], data["overdue"], data["people"]), (0, 0, []))


class FileTests(InsightsTestCase):
    def link(self, task, url, title):
        res = self.client.post(
            f"{API}tasks/{task['id']}/links/", {"title": title, "url": url}
        )
        self.assertEqual(res.status_code, 201, res.content)

    def test_lists_attachments_with_origin_task_and_owner(self):
        task = self.task("Landing")
        self.link(task, "https://drive.google.com/drive/folders/abc", "Assets")
        self.link(task, "https://docs.google.com/document/d/abc", "Copy")
        self.link(task, "https://meet.google.com/abc-defg", "Revisão")
        self.link(task, "https://res.cloudinary.com/x/raw/upload/ata.pdf", "Ata.pdf")
        self.link(task, "https://example.com/brief", "Brief")

        files = {f["title"]: f for f in self.client.get(self.url("files")).json()}

        self.assertEqual(
            {k: v["origin"] for k, v in files.items()},
            {
                "Assets": "drive",
                "Copy": "docs",
                "Revisão": "meet",
                "Ata.pdf": "upload",
                "Brief": "link",
            },
        )
        self.assertEqual(files["Assets"]["task_title"], "Landing")
        self.assertEqual(files["Assets"]["owner_name"], "User")

    def test_organization_level_links_are_included_and_private_sectors_hidden(self):
        task = self.task("Landing")
        self.link(task, "https://drive.google.com/x", "Secret")
        res = self.client.post(
            f"{API}organizations/{self.org.id}/links/",
            {"title": "Manual", "url": "https://example.com/m"},
        )
        self.assertEqual(res.status_code, 201, res.content)

        titles = [f["title"] for f in self.member_client.get(self.url("files")).json()]

        self.assertEqual(titles, ["Manual"])

    def test_deleted_tasks_do_not_leak_their_files(self):
        task = self.task("Gone")
        self.link(task, "https://drive.google.com/x", "Orphan")
        self.assertEqual(
            self.client.delete(f"{API}tasks/{task['id']}/").status_code, 204
        )
        self.assertEqual(self.client.get(self.url("files")).json(), [])
