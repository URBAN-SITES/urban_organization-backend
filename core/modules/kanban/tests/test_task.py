from datetime import timedelta

from django.utils import timezone

from core.modules.kanban.models.task import Status, Task
from core.modules.kanban.tests.helpers import (
    API,
    KanbanTestCase,
    client_for,
    make_user,
)
from core.modules.notifications.models.notification import Notification
from core.modules.organizations.services.organization import OrganizationService


class StatusTests(KanbanTestCase):
    def setUp(self):
        super().setUp()
        self.sector_id = self.make_sector()
        self.url = f"{API}sectors/{self.sector_id}/statuses/"

    def test_create_appends_and_name_is_unique(self):
        res = self.client.post(self.url, {"name": "Review", "category": "in_progress"})
        self.assertEqual((res.status_code, res.json()["position"]), (201, 3))
        res = self.client.post(self.url, {"name": "Review", "category": "todo"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(len(self.client.get(self.url).json()["results"]), 4)

    def test_only_manager_edits_columns(self):
        self.share_sector(self.sector_id, self.member, "editor")
        res = self.member_client.post(self.url, {"name": "X", "category": "todo"})
        self.assertEqual(res.status_code, 403)

    def test_delete_rules(self):
        ids = self.status_ids(self.sector_id)
        self.make_task(self.sector_id)
        res = self.client.delete(f"{self.url}{ids['To do']}/")
        self.assertEqual(res.status_code, 400)  # has tasks
        res = self.client.delete(f"{self.url}{ids['Done']}/")
        self.assertEqual(res.status_code, 400)  # last done column
        res = self.client.delete(f"{self.url}{ids['In progress']}/")
        self.assertEqual(res.status_code, 204)

    def test_changing_category_keeps_completed_at_coherent(self):
        ids = self.status_ids(self.sector_id)
        task = self.make_task(self.sector_id)
        extra = self.client.post(
            self.url, {"name": "Review", "category": "todo"}
        ).json()
        self.client.post(f"{API}tasks/{task['id']}/move/", {"status": extra["id"]})
        self.assertIsNone(Task.objects.get(id=task["id"]).completed_at)
        self.client.patch(f"{self.url}{extra['id']}/", {"category": "done"})
        self.assertIsNotNone(Task.objects.get(id=task["id"]).completed_at)
        self.client.patch(f"{self.url}{extra['id']}/", {"category": "todo"})
        self.assertIsNone(Task.objects.get(id=task["id"]).completed_at)
        self.assertIn("Done", ids)


class TaskTests(KanbanTestCase):
    def setUp(self):
        super().setUp()
        self.sector_id = self.make_sector()
        self.ids = self.status_ids(self.sector_id)
        self.tasks_url = f"{API}sectors/{self.sector_id}/tasks/"

    def move(self, task_id, status, position=None, client=None):
        body = {"status": self.ids.get(status, status)}
        if position is not None:
            body["position"] = position
        return (client or self.client).post(f"{API}tasks/{task_id}/move/", body)

    def test_create_defaults_to_first_todo_column_and_appends(self):
        first = self.make_task(self.sector_id)
        second = self.make_task(self.sector_id)
        self.assertEqual(first["status_id"], self.ids["To do"])
        self.assertEqual((first["position"], second["position"]), (0, 1))
        self.assertIsNone(first["completed_at"])

    def test_create_in_done_column_is_completed(self):
        task = self.make_task(self.sector_id, status=self.ids["Done"])
        self.assertIsNotNone(task["completed_at"])

    def test_status_must_belong_to_the_sector(self):
        other = self.make_sector(name="Other")
        foreign = self.status_ids(other)["Done"]
        res = self.client.post(self.tasks_url, {"title": "x", "status": foreign})
        self.assertEqual(res.status_code, 400)
        task = self.make_task(self.sector_id)
        self.assertEqual(self.move(task["id"], foreign).status_code, 400)

    def test_move_sets_and_clears_completed_at_and_reorders(self):
        a = self.make_task(self.sector_id, title="A")
        b = self.make_task(self.sector_id, title="B")
        c = self.make_task(self.sector_id, title="C")
        done = self.move(a["id"], "Done").json()
        self.assertIsNotNone(done["completed_at"])
        again = self.move(a["id"], "Done").json()  # stays done, keeps the date
        self.assertEqual(again["completed_at"], done["completed_at"])
        back = self.move(a["id"], "To do", position=1).json()
        self.assertIsNone(back["completed_at"])
        order = list(
            Task.objects.filter(status_id=self.ids["To do"]).values_list(
                "title", flat=True
            )
        )
        self.assertEqual(order, ["B", "A", "C"])
        self.assertEqual(b["position"], 1)
        self.assertEqual(c["position"], 2)

    def test_wip_limit(self):
        Status.objects.filter(id=self.ids["In progress"]).update(wip_limit=1)
        a = self.make_task(self.sector_id)
        b = self.make_task(self.sector_id)
        self.assertEqual(self.move(a["id"], "In progress").status_code, 200)
        self.assertEqual(self.move(b["id"], "In progress").status_code, 400)
        # reordering inside the full column is still allowed
        self.assertEqual(self.move(a["id"], "In progress", position=0).status_code, 200)
        res = self.client.post(
            self.tasks_url, {"title": "x", "status": self.ids["In progress"]}
        )
        self.assertEqual(res.status_code, 400)

    def test_patch_edits_fields_but_never_the_column(self):
        task = self.make_task(self.sector_id)
        res = self.client.patch(
            f"{API}tasks/{task['id']}/",
            {"title": "New", "priority": "urgent", "status": self.ids["Done"]},
        )
        self.assertEqual(
            (res.json()["title"], res.json()["priority"]), ("New", "urgent")
        )
        self.assertEqual(res.json()["status_id"], self.ids["To do"])
        self.assertIsNone(res.json()["completed_at"])

    def test_roles_gate_task_writes(self):
        self.share_sector(self.sector_id, self.member, "viewer")
        task = self.make_task(self.sector_id)
        self.assertEqual(
            self.member_client.get(f"{API}tasks/{task['id']}/").status_code, 200
        )
        res = self.member_client.patch(f"{API}tasks/{task['id']}/", {"title": "x"})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(
            self.move(task["id"], "Done", client=self.member_client).status_code, 403
        )
        outsider = client_for(make_user("out@a.com"))
        self.assertEqual(outsider.get(f"{API}tasks/{task['id']}/").status_code, 404)

    def test_assignee_must_participate_and_is_notified(self):
        res = self.client.post(
            self.tasks_url, {"title": "x", "assignee": str(self.member.id)}
        )
        self.assertEqual(res.status_code, 400)  # private sector, not a participant
        self.share_sector(self.sector_id, self.member, "editor")
        task = self.make_task(self.sector_id, assignee=str(self.member.id))
        self.assertEqual(task["assignee_id"], str(self.member.id))
        self.assertEqual(Notification.objects.filter(user=self.member).count(), 1)
        # self-assignment and no-op edits do not notify
        self.client.patch(f"{API}tasks/{task['id']}/", {"assignee": str(self.owner.id)})
        self.client.patch(f"{API}tasks/{task['id']}/", {"title": "again"})
        self.assertEqual(Notification.objects.filter(user=self.owner).count(), 0)
        # unassign
        res = self.client.patch(
            f"{API}tasks/{task['id']}/", {"assignee": None}, format="json"
        )
        self.assertIsNone(res.json()["assignee_id"])

    def test_subtasks_stay_in_the_sector_and_die_with_the_parent(self):
        parent = self.make_task(self.sector_id)
        child = self.make_task(self.sector_id, parent=parent["id"])
        other_sector = self.make_sector(name="Other")
        res = self.client.post(
            f"{API}sectors/{other_sector}/tasks/",
            {"title": "x", "parent": parent["id"]},
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            self.client.delete(f"{API}tasks/{parent['id']}/").status_code, 204
        )
        self.assertFalse(Task.objects.get(id=child["id"]).is_active)
        self.assertEqual(
            self.client.get(f"{API}tasks/{parent['id']}/").status_code, 404
        )

    def test_search_and_filters(self):
        today = timezone.localdate()
        past = (today - timedelta(days=2)).isoformat()
        future = (today + timedelta(days=5)).isoformat()
        self.share_sector(self.sector_id, self.member, "editor")
        late = self.make_task(self.sector_id, title="Fix login", due_date=past)
        soon = self.make_task(
            self.sector_id,
            title="Write docs",
            priority="high",
            due_date=future,
            assignee=str(self.member.id),
        )
        done = self.make_task(
            self.sector_id, title="Ship", status=self.ids["Done"], due_date=past
        )
        sub = self.make_task(self.sector_id, title="Sub", parent=soon["id"])

        def ids(query):
            results = self.client.get(f"{self.tasks_url}?{query}").json()["results"]
            return {task["id"] for task in results}

        self.assertEqual(ids("search=login"), {late["id"]})
        self.assertEqual(ids(f"status={self.ids['Done']}"), {done["id"]})
        self.assertEqual(ids("priority=high"), {soon["id"]})
        self.assertEqual(ids(f"assignee={self.member.id}"), {soon["id"]})
        self.assertEqual(
            ids("overdue=true"), {late["id"]}
        )  # done tasks are never overdue
        self.assertEqual(ids("overdue=false"), {soon["id"], done["id"], sub["id"]})
        self.assertEqual(ids("completed=true"), {done["id"]})
        self.assertEqual(
            ids(f"due_before={today.isoformat()}"), {late["id"], done["id"]}
        )
        self.assertEqual(ids(f"due_after={today.isoformat()}"), {soon["id"]})
        self.assertEqual(
            ids("parent__isnull=true"), {late["id"], soon["id"], done["id"]}
        )
        self.assertEqual(
            self.client.get(f"{self.tasks_url}?status=nope").status_code, 400
        )
        flagged = self.client.get(f"{self.tasks_url}?overdue=true").json()["results"]
        self.assertTrue(flagged[0]["is_overdue"])

    def test_org_member_removed_from_org_cannot_be_assigned(self):
        self.share_sector(self.sector_id, self.member, "editor")
        OrganizationService.remove_member(
            self.owner,
            self.org.id,
            self.org.members.get(user=self.member).id,
        )
        res = self.client.post(
            self.tasks_url, {"title": "x", "assignee": str(self.member.id)}
        )
        self.assertEqual(res.status_code, 400)
