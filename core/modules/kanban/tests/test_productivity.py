from datetime import timedelta

from django.utils import timezone

from core.modules.kanban.models.task import Task
from core.modules.kanban.tests.helpers import API, KanbanTestCase, client_for, make_user
from core.modules.notifications.models.notification import Notification


class TaskKeyTests(KanbanTestCase):
    def test_projects_get_a_key_and_tasks_a_running_number(self):
        res = self.client.post(
            f"{API}organizations/{self.org.id}/sectors/", {"name": "Marketing Digital"}
        )
        sector = res.json()
        self.assertEqual(sector["identifier"], "MD")
        first = self.make_task(sector["id"])
        second = self.make_task(sector["id"])
        self.assertEqual((first["key"], second["key"]), ("MD-1", "MD-2"))
        # deleting does not reuse numbers
        self.client.delete(f"{API}tasks/{second['id']}/")
        self.assertEqual(self.make_task(sector["id"])["key"], "MD-3")
        rows = self.client.get(
            f"{API}sectors/{sector['id']}/tasks/", {"key": "md-1"}
        ).json()["results"]
        self.assertEqual([row["id"] for row in rows], [first["id"]])

    def test_manager_renames_the_key(self):
        sector = self.make_sector(name="Desenvolvimento")
        res = self.client.patch(f"{API}sectors/{sector}/", {"identifier": "web"})
        self.assertEqual(res.json()["identifier"], "WEB")
        res = self.client.patch(f"{API}sectors/{sector}/", {"identifier": "no-way"})
        self.assertEqual(res.status_code, 400)


class EstimateTests(KanbanTestCase):
    def test_estimates_sum_in_the_cycle(self):
        sector = self.make_sector()
        cycle = self.client.post(
            f"{API}sectors/{sector}/cycles/",
            {"name": "S1", "start_date": "2026-01-01", "end_date": "2026-01-14"},
        ).json()
        a = self.make_task(sector, cycle=cycle["id"], estimate=3)
        self.make_task(sector, cycle=cycle["id"], estimate=5)
        self.assertEqual(a["estimate"], 3)
        done = self.status_ids(sector)["Concluído"]
        self.client.post(f"{API}tasks/{a['id']}/move/", {"status": done})
        row = self.client.get(f"{API}sectors/{sector}/cycles/").json()["results"][0]
        self.assertEqual((row["points_total"], row["points_done"]), (8, 3))
        res = self.client.patch(f"{API}tasks/{a['id']}/", {"estimate": 101})
        self.assertEqual(res.status_code, 400)

    def test_burndown_counts_what_was_open_each_day(self):
        sector = self.make_sector()
        today = timezone.localdate()
        cycle = self.client.post(
            f"{API}sectors/{sector}/cycles/",
            {
                "name": "S1",
                "start_date": (today - timedelta(days=2)).isoformat(),
                "end_date": (today + timedelta(days=5)).isoformat(),
            },
        ).json()
        a = self.make_task(sector, cycle=cycle["id"], estimate=2)
        self.make_task(sector, cycle=cycle["id"], estimate=4)
        Task.objects.filter(id=a["id"]).update(
            completed_at=timezone.now() - timedelta(days=1)
        )
        data = self.client.get(f"{API}cycles/{cycle['id']}/burndown/").json()
        self.assertEqual((data["total"], data["total_points"]), (2, 6))
        self.assertEqual(
            [(d["remaining"], d["remaining_points"]) for d in data["days"]],
            [(2, 6), (1, 4), (1, 4)],
        )


class TrashAndArchiveTests(KanbanTestCase):
    def test_deleted_task_comes_back_with_its_subtasks(self):
        sector = self.make_sector()
        parent = self.make_task(sector, title="Pai")
        self.make_task(sector, title="Filha", parent=parent["id"])
        self.client.delete(f"{API}tasks/{parent['id']}/")
        trash = self.client.get(f"{API}sectors/{sector}/trash/").json()["results"]
        self.assertEqual(
            [(t["title"], t["subtask_count"]) for t in trash], [("Pai", 1)]
        )
        res = self.client.post(f"{API}tasks/{parent['id']}/restore/")
        self.assertEqual(res.status_code, 200)
        titles = {
            t["title"]
            for t in self.client.get(f"{API}sectors/{sector}/tasks/").json()["results"]
        }
        self.assertEqual(titles, {"Pai", "Filha"})
        self.assertEqual(
            self.client.get(f"{API}sectors/{sector}/trash/").json()["results"], []
        )

    def test_viewers_cannot_see_or_restore_the_trash(self):
        sector = self.make_sector()
        task = self.make_task(sector)
        self.client.delete(f"{API}tasks/{task['id']}/")
        self.share_sector(sector, self.member, "viewer")
        self.assertEqual(
            self.member_client.get(f"{API}sectors/{sector}/trash/").status_code, 403
        )
        res = self.member_client.post(f"{API}tasks/{task['id']}/restore/")
        self.assertEqual(res.status_code, 403)

    def test_archive_hides_from_board_and_auto_archive_after_days(self):
        sector = self.make_sector()
        a = self.make_task(sector, title="A")
        b = self.make_task(sector, title="B")
        self.client.put(f"{API}tasks/{a['id']}/archive/")
        rows = self.client.get(f"{API}sectors/{sector}/tasks/").json()["results"]
        self.assertEqual([r["title"] for r in rows], ["B"])
        archived = self.client.get(
            f"{API}sectors/{sector}/tasks/", {"archived": "true"}
        ).json()["results"]
        self.assertEqual([r["title"] for r in archived], ["A"])

        self.client.patch(f"{API}sectors/{sector}/", {"auto_archive_days": 7})
        Task.objects.filter(id=b["id"]).update(
            completed_at=timezone.now() - timedelta(days=8)
        )
        rows = self.client.get(f"{API}sectors/{sector}/tasks/").json()["results"]
        self.assertEqual(rows, [])


class FollowTests(KanbanTestCase):
    def test_followers_hear_about_comments_and_moves(self):
        sector = self.make_sector()
        self.share_sector(sector, self.member, "viewer")
        task = self.make_task(sector)
        url = f"{API}tasks/{task['id']}/follow/"
        self.assertEqual(
            self.member_client.get(url).json(), {"following": False, "followers": 1}
        )
        self.assertTrue(self.member_client.put(url).json()["following"])

        self.client.post(f"{API}tasks/{task['id']}/comments/", {"content": "Oi"})
        done = self.status_ids(sector)["Concluído"]
        self.client.post(f"{API}tasks/{task['id']}/move/", {"status": done})
        events = list(
            Notification.objects.filter(user=self.member).values_list(
                "data__event", flat=True
            )
        )
        self.assertCountEqual(events, ["task.commented", "task.status_changed"])
        # the author follows their own task but is not notified of their own actions
        self.assertFalse(Notification.objects.filter(user=self.owner).exists())

        self.member_client.delete(url)
        self.client.post(f"{API}tasks/{task['id']}/comments/", {"content": "De novo"})
        self.assertEqual(Notification.objects.filter(user=self.member).count(), 2)

    def test_outsiders_cannot_follow(self):
        sector = self.make_sector()
        task = self.make_task(sector)
        outsider = client_for(make_user("out@a.com"))
        self.assertEqual(
            outsider.put(f"{API}tasks/{task['id']}/follow/").status_code, 404
        )
