from core.modules.kanban.tests.helpers import API, KanbanTestCase, client_for, make_user


class TaskActivityTests(KanbanTestCase):
    def activity(self, task_id, client=None):
        res = (client or self.client).get(f"{API}tasks/{task_id}/activity/")
        return res

    def test_records_creation_changes_moves_and_comments(self):
        sector = self.make_sector()
        statuses = self.status_ids(sector)
        task = self.make_task(sector, title="Draft")
        self.client.patch(
            f"{API}tasks/{task['id']}/",
            {"title": "Final", "priority": "high", "assignee": str(self.owner.id)},
        )
        self.client.post(
            f"{API}tasks/{task['id']}/move/", {"status": statuses["Em andamento"]}
        )
        self.client.post(f"{API}tasks/{task['id']}/comments/", {"content": "Olá"})

        res = self.activity(task["id"])
        self.assertEqual(res.status_code, 200, res.content)
        rows = res.json()["results"]
        self.assertEqual(
            [r["action"] for r in rows], ["commented", "moved", "updated", "created"]
        )
        update = rows[2]
        self.assertEqual(update["changes"]["title"], ["Draft", "Final"])
        self.assertEqual(update["changes"]["priority"], ["medium", "high"])
        self.assertEqual(update["changes"]["assignee"], [None, "User"])
        self.assertEqual(rows[1]["changes"]["status"], ["A fazer", "Em andamento"])
        self.assertEqual(rows[0]["actor_name"], "User")

    def test_saving_without_changes_adds_nothing(self):
        sector = self.make_sector()
        task = self.make_task(sector, title="Same")
        self.client.patch(f"{API}tasks/{task['id']}/", {"title": "Same"})
        self.assertEqual(len(self.activity(task["id"]).json()["results"]), 1)

    def test_history_follows_task_visibility(self):
        sector = self.make_sector()  # private by default
        task = self.make_task(sector)
        self.assertEqual(self.activity(task["id"], self.member_client).status_code, 404)
        outsider = client_for(make_user("out@b.com"))
        self.assertEqual(self.activity(task["id"], outsider).status_code, 404)
        anonymous = self.client_class()
        self.assertEqual(self.activity(task["id"], anonymous).status_code, 401)

    def test_dashboard_shows_recent_activity_of_visible_projects_only(self):
        visible = self.make_sector(is_private=False)
        hidden = self.make_sector(name="Secret")
        self.make_task(visible, title="Public task")
        self.make_task(hidden, title="Secret task")
        res = self.member_client.get(f"{API}organizations/{self.org.id}/dashboard/")
        titles = [a["task_title"] for a in res.json()["recent_activity"]]
        self.assertEqual(titles, ["Public task"])


class SectorFavoriteArchiveTests(KanbanTestCase):
    def list_sectors(self, client=None, **params):
        res = (client or self.client).get(
            f"{API}organizations/{self.org.id}/sectors/", params
        )
        self.assertEqual(res.status_code, 200, res.content)
        return {s["name"]: s for s in res.json()["results"]}

    def test_favorite_is_per_user_and_idempotent(self):
        sector = self.make_sector(is_private=False)
        for _ in range(2):
            res = self.client.put(f"{API}sectors/{sector}/favorite/")
            self.assertEqual(res.status_code, 200, res.content)
            self.assertTrue(res.json()["is_favorite"])
        self.assertTrue(self.list_sectors()["Board"]["is_favorite"])
        self.assertFalse(self.list_sectors(self.member_client)["Board"]["is_favorite"])

        dashboard = self.client.get(f"{API}organizations/{self.org.id}/dashboard/")
        self.assertEqual([f["name"] for f in dashboard.json()["favorites"]], ["Board"])

        self.assertEqual(
            self.client.delete(f"{API}sectors/{sector}/favorite/").status_code, 204
        )
        self.assertFalse(self.list_sectors()["Board"]["is_favorite"])

    def test_cannot_favorite_a_sector_you_cannot_see(self):
        sector = self.make_sector()  # private
        res = self.member_client.put(f"{API}sectors/{sector}/favorite/")
        self.assertEqual(res.status_code, 404)

    def test_list_reports_progress(self):
        sector = self.make_sector()
        statuses = self.status_ids(sector)
        done = self.make_task(sector)
        self.make_task(sector)
        self.client.post(
            f"{API}tasks/{done['id']}/move/", {"status": statuses["Concluído"]}
        )
        row = self.list_sectors()["Board"]
        self.assertEqual((row["task_total"], row["task_done"]), (2, 1))

    def test_archive_hides_from_lists_and_restore_brings_back(self):
        sector = self.make_sector()
        res = self.client.put(f"{API}sectors/{sector}/archive/")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertIsNotNone(res.json()["archived_at"])
        self.assertNotIn("Board", self.list_sectors())
        self.assertIn("Board", self.list_sectors(archived="true"))
        # still reachable directly (links keep working)
        self.assertEqual(self.client.get(f"{API}sectors/{sector}/").status_code, 200)

        res = self.client.delete(f"{API}sectors/{sector}/archive/")
        self.assertIsNone(res.json()["archived_at"])
        self.assertIn("Board", self.list_sectors())

    def test_only_managers_archive(self):
        sector = self.make_sector()
        self.share_sector(sector, self.member, "editor")
        res = self.member_client.put(f"{API}sectors/{sector}/archive/")
        self.assertEqual(res.status_code, 403)
