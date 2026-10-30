from datetime import timedelta

from django.utils import timezone

from core.modules.kanban.models.sector import Sector
from core.modules.kanban.tests.helpers import API, KanbanTestCase, client_for, make_user
from core.modules.meetings.models.insight import MeetingInsight
from core.modules.meetings.models.meeting import Meeting, MeetingRecording


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

    def test_dashboard_lists_meetings_and_summaries_of_visible_projects(self):
        visible = Sector.objects.get(id=self.make_sector(is_private=False))
        hidden = Sector.objects.get(id=self.make_sector(name="Secret"))
        now = timezone.now()

        def meeting(sector, title, start):
            m = Meeting.objects.create(
                sector=sector,
                title=title,
                starts_at=start,
                ends_at=start + timedelta(hours=1),
                created_by=self.owner,
            )
            m.participants.add(self.owner, self.member)
            return m

        later = meeting(visible, "Later", now + timedelta(days=2))
        meeting(visible, "Soon", now + timedelta(hours=1))
        meeting(visible, "Past", now - timedelta(days=2))
        meeting(hidden, "Hidden", now + timedelta(hours=2))
        recording = MeetingRecording.objects.create(
            meeting=later, egress_id="EG_dash", file_key="k", duration_seconds=90
        )
        MeetingInsight.objects.create(
            recording=recording,
            transcribe_model="m",
            status=MeetingInsight.Status.DONE,
            finished_at=now,
            summary={"executive_summary": "Resumo.", "actions": [{}, {}]},
        )

        data = self.member_client.get(
            f"{API}organizations/{self.org.id}/dashboard/"
        ).json()
        self.assertEqual(
            [m["title"] for m in data["upcoming_meetings"]], ["Soon", "Later"]
        )
        self.assertEqual(data["upcoming_meetings"][0]["participant_count"], 2)
        self.assertEqual(len(data["recent_insights"]), 1)
        self.assertEqual(data["recent_insights"][0]["excerpt"], "Resumo.")
        self.assertEqual(data["recent_insights"][0]["action_count"], 2)
        self.assertEqual(data["members"], 2)
        self.assertEqual(data["my_in_progress"], [])
        self.assertEqual(data["my_done"], [])

    def test_dashboard_lists_my_tasks_in_progress_and_done(self):
        sector = self.make_sector()
        statuses = self.status_ids(sector)
        mine = str(self.owner.id)
        doing = self.make_task(sector, title="Doing", assignee=mine)
        finished = self.make_task(sector, title="Finished", assignee=mine)
        self.make_task(sector, title="Not mine")
        self.client.post(
            f"{API}tasks/{doing['id']}/move/", {"status": statuses["Em andamento"]}
        )
        self.client.post(
            f"{API}tasks/{finished['id']}/move/", {"status": statuses["Concluído"]}
        )

        data = self.client.get(f"{API}organizations/{self.org.id}/dashboard/").json()
        self.assertEqual([t["title"] for t in data["my_in_progress"]], ["Doing"])
        self.assertEqual([t["title"] for t in data["my_done"]], ["Finished"])
        self.assertIsNotNone(data["my_done"][0]["completed_at"])


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


class SectorListFilterTests(KanbanTestCase):
    def names(self, client=None, **params):
        res = (client or self.client).get(
            f"{API}organizations/{self.org.id}/sectors/", params
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertIn("count", res.json())  # paginated by the server
        return [s["name"] for s in res.json()["results"]]

    def test_search_favorite_and_ordering_run_on_the_server(self):
        self.make_sector(name="Marketing", description="campanhas")
        site = self.make_sector(name="Site")
        self.make_sector(name="Design")
        self.assertEqual(self.names(), ["Design", "Marketing", "Site"])
        self.assertEqual(self.names(ordering="-name"), ["Site", "Marketing", "Design"])
        self.assertEqual(self.names(ordering="-created_at")[0], "Design")
        self.assertEqual(self.names(search="CAMPAN"), ["Marketing"])
        self.client.put(f"{API}sectors/{site}/favorite/")
        self.assertEqual(self.names(favorite="true"), ["Site"])

    def test_rejects_unknown_ordering(self):
        res = self.client.get(
            f"{API}organizations/{self.org.id}/sectors/", {"ordering": "owner__email"}
        )
        self.assertEqual(res.status_code, 400)

    def test_can_manage_follows_the_effective_role(self):
        mine = self.make_sector(name="Mine", client=self.member_client)
        shared = self.make_sector(name="Shared")
        self.share_sector(shared, self.member, "editor")
        rows = {
            s["name"]: s["can_manage"]
            for s in self.member_client.get(
                f"{API}organizations/{self.org.id}/sectors/"
            ).json()["results"]
        }
        self.assertEqual(rows, {"Mine": True, "Shared": False})
        owner_rows = self.client.get(
            f"{API}organizations/{self.org.id}/sectors/"
        ).json()["results"]
        self.assertTrue(all(s["can_manage"] for s in owner_rows))  # org owner
        detail = self.member_client.get(f"{API}sectors/{mine}/").json()
        self.assertTrue(detail["can_manage"])

    def test_outsiders_cannot_list(self):
        outsider = client_for(make_user("out@a.com"))
        res = outsider.get(f"{API}organizations/{self.org.id}/sectors/")
        self.assertIn(res.status_code, (403, 404))

    def test_color_and_icon_are_validated(self):
        url = f"{API}organizations/{self.org.id}/sectors/"
        for bad in ({"color": "red"}, {"color": "#12345"}, {"icon": "<svg>"}):
            res = self.client.post(url, {"name": "X", **bad})
            self.assertEqual(res.status_code, 400, bad)
        res = self.client.post(url, {"name": "X", "color": "#0EA5E9", "icon": "rocket"})
        self.assertEqual(res.status_code, 201, res.content)
