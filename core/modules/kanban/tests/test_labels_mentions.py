from core.modules.kanban.tests.helpers import API, KanbanTestCase, client_for, make_user
from core.modules.notifications.models.notification import Notification


class LabelTests(KanbanTestCase):
    def make_label(self, sector, client=None, **data):
        res = (client or self.client).post(
            f"{API}sectors/{sector}/labels/",
            {"name": "Bug", "color": "#ef4444", **data},
        )
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()["id"]

    def test_crud_and_unique_name_per_project(self):
        sector = self.make_sector()
        label = self.make_label(sector)
        res = self.client.post(f"{API}sectors/{sector}/labels/", {"name": "bug"})
        self.assertEqual(res.status_code, 400)  # case-insensitive duplicate
        res = self.client.patch(f"{API}labels/{label}/", {"name": "Erro"})
        self.assertEqual(res.json()["name"], "Erro")
        res = self.client.get(f"{API}sectors/{sector}/labels/")
        self.assertEqual([row["name"] for row in res.json()["results"]], ["Erro"])
        self.assertEqual(self.client.delete(f"{API}labels/{label}/").status_code, 204)

    def test_viewers_read_but_cannot_write(self):
        sector = self.make_sector()
        label = self.make_label(sector)
        self.share_sector(sector, self.member, "viewer")
        res = self.member_client.get(f"{API}sectors/{sector}/labels/")
        self.assertEqual(res.status_code, 200)
        res = self.member_client.post(f"{API}sectors/{sector}/labels/", {"name": "X"})
        self.assertEqual(res.status_code, 403)
        res = self.member_client.delete(f"{API}labels/{label}/")
        self.assertEqual(res.status_code, 403)
        outsider = client_for(make_user("out@a.com"))
        self.assertEqual(outsider.get(f"{API}labels/{label}/").status_code, 405)
        self.assertEqual(outsider.delete(f"{API}labels/{label}/").status_code, 404)

    def test_tasks_take_labels_of_their_project_only(self):
        sector = self.make_sector()
        other = self.make_sector(name="Other")
        bug = self.make_label(sector)
        foreign = self.make_label(other, name="Foreign")
        task = self.make_task(sector, label_ids=[bug])
        self.assertEqual([lb["name"] for lb in task["labels"]], ["Bug"])

        res = self.client.patch(
            f"{API}tasks/{task['id']}/", {"label_ids": [foreign]}, format="json"
        )
        self.assertEqual(res.status_code, 400)

        res = self.client.patch(
            f"{API}tasks/{task['id']}/", {"label_ids": []}, format="json"
        )
        self.assertEqual(res.json()["labels"], [])
        history = self.client.get(f"{API}tasks/{task['id']}/activity/").json()
        self.assertIn(
            {"labels": ["Bug", None]}, [row["changes"] for row in history["results"]]
        )

    def test_filter_tasks_by_label(self):
        sector = self.make_sector()
        bug = self.make_label(sector)
        self.make_task(sector, title="With", label_ids=[bug])
        self.make_task(sector, title="Without")
        res = self.client.get(f"{API}sectors/{sector}/tasks/", {"label": bug})
        self.assertEqual([t["title"] for t in res.json()["results"]], ["With"])


class SubtaskTests(KanbanTestCase):
    def test_counts_and_listing_by_parent(self):
        sector = self.make_sector()
        statuses = self.status_ids(sector)
        parent = self.make_task(sector, title="Parent")
        done = self.make_task(sector, title="Child 1", parent=parent["id"])
        self.make_task(sector, title="Child 2", parent=parent["id"])
        self.client.post(
            f"{API}tasks/{done['id']}/move/", {"status": statuses["Concluído"]}
        )
        rows = self.client.get(
            f"{API}sectors/{sector}/tasks/", {"parent__isnull": "true"}
        ).json()["results"]
        self.assertEqual(
            [(r["title"], r["subtask_total"], r["subtask_done"]) for r in rows],
            [("Parent", 2, 1)],
        )
        children = self.client.get(
            f"{API}sectors/{sector}/tasks/", {"parent": parent["id"]}
        ).json()["results"]
        self.assertEqual(len(children), 2)


class MentionTests(KanbanTestCase):
    def comment(self, task_id, client=None, **data):
        return (client or self.client).post(
            f"{API}tasks/{task_id}/comments/", data, format="json"
        )

    def test_mention_notifies_people_with_access(self):
        sector = self.make_sector()
        self.share_sector(sector, self.member, "viewer")
        task = self.make_task(sector)
        res = self.comment(
            task["id"], content="@User pode revisar?", mentions=[str(self.member.id)]
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(
            [m["id"] for m in res.json()["mentions"]], [str(self.member.id)]
        )
        notification = Notification.objects.get(user=self.member)
        self.assertEqual(notification.data["event"], "task.mentioned")
        listed = self.client.get(f"{API}tasks/{task['id']}/comments/").json()
        self.assertEqual(len(listed["results"][0]["mentions"]), 1)

    def test_cannot_mention_someone_without_access(self):
        sector = self.make_sector()  # private: member has no access
        task = self.make_task(sector)
        res = self.comment(task["id"], content="oi", mentions=[str(self.member.id)])
        self.assertEqual(res.status_code, 400)
        self.assertFalse(Notification.objects.filter(user=self.member).exists())

    def test_self_mention_is_kept_but_not_notified(self):
        sector = self.make_sector()
        task = self.make_task(sector)
        res = self.comment(task["id"], content="nota", mentions=[str(self.owner.id)])
        self.assertEqual(res.status_code, 201)
        self.assertFalse(Notification.objects.filter(user=self.owner).exists())

    def test_edit_keeps_mentions_unless_sent_and_notifies_only_new(self):
        sector = self.make_sector()
        self.share_sector(sector, self.member, "viewer")
        task = self.make_task(sector)
        member = [str(self.member.id)]
        comment = self.comment(task["id"], content="@User", mentions=member).json()
        url = f"{API}tasks/{task['id']}/comments/{comment['id']}/"
        res = self.client.patch(url, {"content": "@User ok"}, format="json")
        self.assertEqual(len(res.json()["mentions"]), 1)
        self.client.patch(url, {"content": "@User", "mentions": member}, format="json")
        self.assertEqual(Notification.objects.filter(user=self.member).count(), 1)
        res = self.client.patch(url, {"content": "x", "mentions": []}, format="json")
        self.assertEqual(res.json()["mentions"], [])


class SectorPeopleTests(KanbanTestCase):
    def test_lists_everyone_with_access(self):
        sector = self.make_sector()
        self.share_sector(sector, self.member)
        self.add_org_member("other@a.com")  # no access to the private sector
        res = self.client.get(f"{API}sectors/{sector}/people/")
        self.assertEqual(res.status_code, 200)
        emails = {p["email"] for p in res.json()["results"]}
        self.assertEqual(emails, {"owner@a.com", "member@a.com"})

    def test_outsider_gets_404(self):
        sector = self.make_sector()
        outsider = client_for(make_user("out@a.com"))
        self.assertEqual(
            outsider.get(f"{API}sectors/{sector}/people/").status_code, 404
        )


class TaskServerFilterTests(KanbanTestCase):
    def titles(self, sector, **params):
        res = self.client.get(f"{API}sectors/{sector}/tasks/", params)
        self.assertEqual(res.status_code, 200, res.content)
        return sorted(t["title"] for t in res.json()["results"])

    def test_unassigned_undated_and_priority_set(self):
        sector = self.make_sector()
        self.make_task(
            sector, title="Mine", assignee=str(self.owner.id), due_date="2030-01-01"
        )
        self.make_task(sector, title="Loose", priority="urgent")
        self.make_task(sector, title="High", priority="high", due_date="2030-01-02")
        self.assertEqual(
            self.titles(sector, assignee__isnull="true"), ["High", "Loose"]
        )
        self.assertEqual(self.titles(sector, due_date__isnull="true"), ["Loose"])
        self.assertEqual(
            self.titles(sector, priority__in="high,urgent"), ["High", "Loose"]
        )
