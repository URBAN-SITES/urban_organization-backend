from datetime import date, timedelta

from django.utils import timezone

from core.modules.kanban.models.activity import TaskActivity
from core.modules.kanban.tests.helpers import API, KanbanTestCase, client_for, make_user


class CycleTests(KanbanTestCase):
    def make_cycle(self, sector, client=None, **data):
        today = timezone.localdate()
        body = {
            "name": "Sprint 1",
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=13)).isoformat(),
            **data,
        }
        res = (client or self.client).post(f"{API}sectors/{sector}/cycles/", body)
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()

    def test_create_list_and_progress(self):
        sector = self.make_sector()
        cycle = self.make_cycle(sector)
        self.assertEqual(cycle["state"], "current")
        self.assertEqual((cycle["task_total"], cycle["task_done"]), (0, 0))

        task = self.make_task(sector, cycle=cycle["id"])
        self.assertEqual(task["cycle_id"], cycle["id"])
        self.make_task(sector, cycle=cycle["id"])
        done = self.status_ids(sector)["Concluído"]
        self.client.post(f"{API}tasks/{task['id']}/move/", {"status": done})

        rows = self.client.get(f"{API}sectors/{sector}/cycles/").json()["results"]
        self.assertEqual((rows[0]["task_total"], rows[0]["task_done"]), (2, 1))
        listed = self.client.get(
            f"{API}sectors/{sector}/tasks/", {"cycle": cycle["id"]}
        ).json()["results"]
        self.assertEqual(len(listed), 2)

    def test_state_follows_the_dates(self):
        sector = self.make_sector()
        past = self.make_cycle(sector, start_date="2020-01-01", end_date="2020-01-14")
        future = self.make_cycle(sector, start_date="2999-01-01", end_date="2999-01-14")
        self.assertEqual(past["state"], "completed")
        self.assertEqual(future["state"], "upcoming")

    def test_end_before_start_is_rejected(self):
        sector = self.make_sector()
        res = self.client.post(
            f"{API}sectors/{sector}/cycles/",
            {"name": "X", "start_date": "2026-02-10", "end_date": "2026-02-01"},
        )
        self.assertEqual(res.status_code, 400)
        cycle = self.make_cycle(sector)
        res = self.client.patch(
            f"{API}cycles/{cycle['id']}/", {"end_date": "2000-01-01"}
        )
        self.assertEqual(res.status_code, 400)

    def test_delete_keeps_the_tasks(self):
        sector = self.make_sector()
        cycle = self.make_cycle(sector)
        task = self.make_task(sector, cycle=cycle["id"])
        self.assertEqual(
            self.client.delete(f"{API}cycles/{cycle['id']}/").status_code, 204
        )
        res = self.client.get(f"{API}tasks/{task['id']}/")
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.json()["cycle_id"])

    def test_task_only_takes_a_cycle_of_its_project(self):
        sector = self.make_sector()
        other = self.make_sector(name="Other")
        foreign = self.make_cycle(other)
        res = self.client.post(
            f"{API}sectors/{sector}/tasks/", {"title": "T", "cycle": foreign["id"]}
        )
        self.assertEqual(res.status_code, 400)
        task = self.make_task(sector)
        res = self.client.patch(f"{API}tasks/{task['id']}/", {"cycle": foreign["id"]})
        self.assertEqual(res.status_code, 400)

    def test_viewers_read_and_outsiders_see_nothing(self):
        sector = self.make_sector()
        cycle = self.make_cycle(sector)
        self.share_sector(sector, self.member, "viewer")
        res = self.member_client.get(f"{API}sectors/{sector}/cycles/")
        self.assertEqual(res.status_code, 200)
        res = self.member_client.patch(f"{API}cycles/{cycle['id']}/", {"name": "Y"})
        self.assertEqual(res.status_code, 403)
        outsider = client_for(make_user("out@a.com"))
        self.assertEqual(
            outsider.delete(f"{API}cycles/{cycle['id']}/").status_code, 404
        )


class TaskDatesTests(KanbanTestCase):
    def test_start_date_is_saved_and_logged(self):
        sector = self.make_sector()
        task = self.make_task(sector, start_date="2026-03-01", due_date="2026-03-10")
        self.assertEqual(task["start_date"], "2026-03-01")
        res = self.client.patch(
            f"{API}tasks/{task['id']}/", {"start_date": "2026-03-05"}
        )
        self.assertEqual(res.status_code, 200)
        log = TaskActivity.objects.filter(task_id=task["id"]).first()
        self.assertEqual(log.changes["start_date"], ["2026-03-01", "2026-03-05"])

    def test_start_after_due_is_rejected(self):
        sector = self.make_sector()
        res = self.client.post(
            f"{API}sectors/{sector}/tasks/",
            {"title": "T", "start_date": "2026-03-10", "due_date": "2026-03-01"},
        )
        self.assertEqual(res.status_code, 400)
        task = self.make_task(sector, due_date=date(2026, 3, 1).isoformat())
        res = self.client.patch(
            f"{API}tasks/{task['id']}/", {"start_date": "2026-04-01"}
        )
        self.assertEqual(res.status_code, 400)


class RelationTests(KanbanTestCase):
    def relate(self, task, other, kind="blocked_by", client=None):
        return (client or self.client).post(
            f"{API}tasks/{task}/relations/", {"kind": kind, "task": other}
        )

    def test_blocked_by_and_blocking_are_two_views_of_one_link(self):
        sector = self.make_sector()
        design = self.make_task(sector, title="Design")
        build = self.make_task(sector, title="Build")
        res = self.relate(build["id"], design["id"])
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual([t["title"] for t in res.json()["blocked_by"]], ["Design"])

        other_side = self.client.get(f"{API}tasks/{design['id']}/relations/").json()
        self.assertEqual([t["title"] for t in other_side["blocking"]], ["Build"])

        # the blocked task says so until its blocker is done
        rows = self.client.get(f"{API}sectors/{sector}/tasks/").json()["results"]
        blocked = {row["title"]: row["is_blocked"] for row in rows}
        self.assertEqual(blocked, {"Design": False, "Build": True})
        done = self.status_ids(sector)["Concluído"]
        self.client.post(f"{API}tasks/{design['id']}/move/", {"status": done})
        self.assertFalse(
            self.client.get(f"{API}tasks/{build['id']}/").json()["is_blocked"]
        )

    def test_rejects_self_duplicates_loops_and_other_projects(self):
        sector = self.make_sector()
        a = self.make_task(sector, title="A")["id"]
        b = self.make_task(sector, title="B")["id"]
        c = self.make_task(sector, title="C")["id"]
        foreign = self.make_task(self.make_sector(name="Other"))["id"]
        self.assertEqual(self.relate(a, a).status_code, 400)
        self.assertEqual(self.relate(a, foreign).status_code, 400)
        self.assertEqual(self.relate(b, a).status_code, 201)  # A blocks B
        self.assertEqual(self.relate(b, a).status_code, 400)  # duplicate
        self.assertEqual(self.relate(a, b, "blocking").status_code, 400)  # same link
        self.assertEqual(self.relate(c, b).status_code, 201)  # B blocks C
        self.assertEqual(self.relate(a, c).status_code, 400)  # C blocks A: loop

    def test_remove_and_permissions(self):
        sector = self.make_sector()
        a = self.make_task(sector, title="A")["id"]
        b = self.make_task(sector, title="B")["id"]
        self.relate(a, b)
        self.share_sector(sector, self.member, "viewer")
        res = self.member_client.get(f"{API}tasks/{a}/relations/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.relate(a, b, client=self.member_client).status_code, 403)
        res = self.member_client.delete(f"{API}tasks/{a}/relations/{b}/")
        self.assertEqual(res.status_code, 403)
        # removable from either side
        self.assertEqual(
            self.client.delete(f"{API}tasks/{b}/relations/{a}/").status_code, 204
        )
        self.assertEqual(
            self.client.delete(f"{API}tasks/{b}/relations/{a}/").status_code, 404
        )
        self.assertEqual(
            self.client.get(f"{API}tasks/{a}/relations/").json()["blocked_by"], []
        )
