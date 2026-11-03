from datetime import date

from core.modules.kanban.models.task import Task
from core.modules.kanban.services.task import TaskService
from core.modules.kanban.tests.helpers import API, KanbanTestCase


class SavedViewTests(KanbanTestCase):
    def test_private_views_stay_with_their_owner(self):
        sector = self.make_sector()
        self.share_sector(sector, self.member, "viewer")
        url = f"{API}sectors/{sector}/views/"
        res = self.member_client.post(
            url,
            {"name": "Minhas", "layout": "list", "filters": {"priority": "high"}},
            format="json",
        )
        self.assertEqual(res.status_code, 403)  # is_shared defaults to true: editor+
        res = self.member_client.post(
            url, {"name": "Minhas", "layout": "list", "is_shared": False}, format="json"
        )
        self.assertEqual(res.status_code, 201, res.content)
        mine = res.json()["id"]
        shared = self.client.post(url, {"name": "Time"}, format="json").json()
        self.assertEqual(
            {row["name"] for row in self.member_client.get(url).json()},
            {"Minhas", "Time"},
        )
        self.assertEqual([row["name"] for row in self.client.get(url).json()], ["Time"])
        res = self.member_client.patch(f"{API}views/{shared['id']}/", {"name": "x"})
        self.assertEqual(res.status_code, 403)
        res = self.member_client.patch(
            f"{API}views/{mine}/", {"is_shared": True}, format="json"
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(self.client.delete(f"{API}views/{mine}/").status_code, 404)


class CustomFieldTests(KanbanTestCase):
    def test_values_are_checked_by_type(self):
        sector = self.make_sector()
        url = f"{API}sectors/{sector}/fields/"
        number = self.client.post(url, {"name": "Custo", "type": "number"}).json()
        select = self.client.post(
            url,
            {
                "name": "Cliente",
                "type": "select",
                "options": [{"name": "Acme"}, {"name": "Beta", "color": "#00aa00"}],
            },
            format="json",
        ).json()
        self.assertEqual([o["name"] for o in select["options"]], ["Acme", "Beta"])
        dup = self.client.post(url, {"name": "custo", "type": "text"})
        self.assertEqual(dup.status_code, 400)

        task = self.make_task(sector)
        field_url = f"{API}tasks/{task['id']}/fields/"
        res = self.client.put(
            f"{field_url}{number['id']}/", {"value": "12.5"}, format="json"
        )
        self.assertEqual(res.json()["value"], 12.5)
        bad = self.client.put(
            f"{field_url}{number['id']}/", {"value": "a"}, format="json"
        )
        self.assertEqual(bad.status_code, 400)
        option = select["options"][1]["id"]
        self.client.put(f"{field_url}{select['id']}/", {"value": option}, format="json")
        values = {
            row["field_id"]: row["value"] for row in self.client.get(field_url).json()
        }
        self.assertEqual(values, {number["id"]: 12.5, select["id"]: option})
        self.client.put(f"{field_url}{number['id']}/", {"value": None}, format="json")
        self.assertEqual(len(self.client.get(field_url).json()), 1)

    def test_only_managers_shape_fields(self):
        sector = self.make_sector()
        self.share_sector(sector, self.member, "editor")
        res = self.member_client.post(
            f"{API}sectors/{sector}/fields/", {"name": "X", "type": "text"}
        )
        self.assertEqual(res.status_code, 403)


class TemplateTests(KanbanTestCase):
    def test_task_created_from_a_template_brings_its_checklist(self):
        sector = self.make_sector()
        label = self.client.post(
            f"{API}sectors/{sector}/labels/", {"name": "bug"}
        ).json()
        tpl = self.client.post(
            f"{API}sectors/{sector}/templates/",
            {
                "name": "Bug",
                "title": "Bug: ",
                "priority": "high",
                "label_ids": [label["id"]],
                "checklist": ["Reproduzir", "Corrigir"],
            },
            format="json",
        )
        self.assertEqual(tpl.status_code, 201, tpl.content)
        task = self.client.post(
            f"{API}sectors/{sector}/tasks/",
            {"title": "Bug: login", "checklist": ["Reproduzir", "Corrigir"]},
            format="json",
        ).json()
        self.assertEqual(task["checklist_total"], 2)


class RecurrenceTests(KanbanTestCase):
    def test_next_dates(self):
        self.assertEqual(
            TaskService.next_date(date(2026, 1, 31), "monthly"), date(2026, 2, 28)
        )
        self.assertEqual(
            TaskService.next_date(date(2026, 12, 15), "monthly"), date(2027, 1, 15)
        )
        self.assertEqual(
            TaskService.next_date(date(2026, 1, 1), "weekly"), date(2026, 1, 8)
        )

    def test_completing_a_repeating_task_opens_the_next_one(self):
        sector = self.make_sector()
        task = self.make_task(
            sector, recurrence="weekly", start_date="2026-03-01", due_date="2026-03-03"
        )
        self.assertEqual(task["recurrence"], "weekly")
        done = self.status_ids(sector)["Concluído"]
        self.client.post(f"{API}tasks/{task['id']}/move/", {"status": done})
        nxt = Task.objects.exclude(id=task["id"]).get(sector_id=sector)
        self.assertEqual(
            (nxt.start_date, nxt.due_date), (date(2026, 3, 8), date(2026, 3, 10))
        )
        self.assertEqual(nxt.recurrence, "weekly")
        self.assertIsNone(nxt.completed_at)
        self.assertEqual(Task.objects.get(id=task["id"]).recurrence, "")


class BulkTests(KanbanTestCase):
    def test_bulk_changes_many_tasks(self):
        sector = self.make_sector()
        a, b = self.make_task(sector), self.make_task(sector)
        url = f"{API}sectors/{sector}/tasks/bulk/"
        done = self.status_ids(sector)["Concluído"]
        res = self.client.post(
            url,
            {"task_ids": [a["id"], b["id"]], "status": done, "priority": "urgent"},
            format="json",
        )
        self.assertEqual(res.json(), {"updated": 2})
        rows = Task.objects.filter(sector_id=sector)
        self.assertTrue(all(t.completed_at and t.priority == "urgent" for t in rows))
        other = self.make_task(self.make_sector(name="Outro"))
        res = self.client.post(
            url, {"task_ids": [a["id"], other["id"]], "archive": True}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        res = self.client.post(
            url, {"task_ids": [a["id"]], "delete": True}, format="json"
        )
        self.assertEqual(res.json(), {"updated": 1})
        self.assertFalse(Task.objects.get(id=a["id"]).is_active)

    def test_viewers_cannot_bulk_edit(self):
        sector = self.make_sector()
        self.share_sector(sector, self.member, "viewer")
        task = self.make_task(sector)
        res = self.member_client.post(
            f"{API}sectors/{sector}/tasks/bulk/",
            {"task_ids": [task["id"]], "priority": "low"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)
