from core.modules.kanban.models.intake import IntakeRequest
from core.modules.kanban.models.task import Task
from core.modules.kanban.tests.helpers import API, KanbanTestCase
from core.modules.notifications.models.notification import Notification


class EpicTests(KanbanTestCase):
    def test_epic_groups_tasks_and_counts_progress(self):
        sector = self.make_sector()
        res = self.client.post(
            f"{API}sectors/{sector}/epics/",
            {
                "name": "Checkout novo",
                "state": "in_progress",
                "lead": str(self.owner.id),
                "start_date": "2026-01-01",
                "target_date": "2026-02-01",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.content)
        epic = res.json()
        self.assertEqual(epic["lead_id"], str(self.owner.id))
        a = self.make_task(sector, epic=epic["id"], estimate=3)
        self.make_task(sector, epic=epic["id"])
        self.assertEqual(a["epic_id"], epic["id"])
        done = self.status_ids(sector)["Concluído"]
        self.client.post(f"{API}tasks/{a['id']}/move/", {"status": done})
        row = self.client.get(f"{API}sectors/{sector}/epics/").json()[0]
        self.assertEqual((row["task_total"], row["task_done"]), (2, 1))
        rows = self.client.get(
            f"{API}sectors/{sector}/tasks/", {"epic": epic["id"]}
        ).json()["results"]
        self.assertEqual(len(rows), 2)
        # tasks stay when the epic goes
        self.client.delete(f"{API}epics/{epic['id']}/")
        self.assertIsNone(Task.objects.get(id=a["id"]).epic_id)

    def test_epic_of_another_project_is_refused(self):
        sector = self.make_sector()
        other = self.make_sector(name="Outro")
        epic = self.client.post(f"{API}sectors/{other}/epics/", {"name": "E"}).json()
        res = self.client.post(
            f"{API}sectors/{sector}/tasks/", {"title": "x", "epic": epic["id"]}
        )
        self.assertEqual(res.status_code, 400)
        res = self.client.post(
            f"{API}sectors/{sector}/epics/",
            {"name": "E", "start_date": "2026-02-01", "target_date": "2026-01-01"},
        )
        self.assertEqual(res.status_code, 400)


class PageTests(KanbanTestCase):
    def test_editors_write_and_viewers_read(self):
        sector = self.make_sector()
        self.share_sector(sector, self.member, "viewer")
        url = f"{API}sectors/{sector}/pages/"
        page = self.client.post(
            url, {"title": "Decisões", "content": "# Stack\n\nVue e Django."}
        ).json()
        rows = self.member_client.get(url).json()
        self.assertEqual(rows[0]["excerpt"], "Stack Vue e Django.")
        read = self.member_client.get(f"{API}pages/{page['id']}/").json()
        self.assertEqual(read["content"], "# Stack\n\nVue e Django.")
        res = self.member_client.patch(f"{API}pages/{page['id']}/", {"title": "x"})
        self.assertEqual(res.status_code, 403)
        res = self.client.patch(f"{API}pages/{page['id']}/", {"is_pinned": True})
        self.assertTrue(res.json()["is_pinned"])


class IntakeTests(KanbanTestCase):
    def test_viewer_asks_and_editor_accepts(self):
        sector = self.make_sector()
        self.share_sector(sector, self.member, "viewer")
        url = f"{API}sectors/{sector}/intake/"
        res = self.member_client.post(
            url, {"title": "Arrumar o site", "description": "O menu some no celular."}
        )
        self.assertEqual(res.status_code, 201, res.content)
        request = res.json()
        self.assertTrue(
            Notification.objects.filter(
                user=self.owner, data__event="intake.created"
            ).exists()
        )
        # viewers cannot answer
        res = self.member_client.post(f"{API}intake/{request['id']}/accept/")
        self.assertEqual(res.status_code, 403)
        res = self.client.post(
            f"{API}intake/{request['id']}/accept/", {"priority": "high"}
        )
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        self.assertEqual(data["state"], "accepted")
        task = Task.objects.get(id=data["task_id"])
        self.assertEqual((task.title, task.priority), ("Arrumar o site", "high"))
        self.assertTrue(task.subscribers.filter(user=self.member).exists())
        self.assertTrue(
            Notification.objects.filter(
                user=self.member, data__event="intake.accepted"
            ).exists()
        )
        again = self.client.post(f"{API}intake/{request['id']}/decline/")
        self.assertEqual(again.status_code, 400)

    def test_viewers_only_see_their_own_requests(self):
        sector = self.make_sector()
        self.share_sector(sector, self.member, "viewer")
        url = f"{API}sectors/{sector}/intake/"
        self.client.post(url, {"title": "Do dono"})
        mine = self.member_client.post(url, {"title": "Meu"}).json()
        self.assertEqual(
            [row["title"] for row in self.member_client.get(url).json()], ["Meu"]
        )
        self.assertEqual(len(self.client.get(url).json()), 2)
        res = self.client.post(
            f"{API}intake/{mine['id']}/decline/", {"note": "Já existe."}
        )
        self.assertEqual(res.json()["decision_note"], "Já existe.")
        self.assertEqual(
            IntakeRequest.objects.get(id=mine["id"]).state, IntakeRequest.State.DECLINED
        )
