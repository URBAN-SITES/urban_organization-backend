import json
from datetime import timedelta

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models.user import User
from core.modules.kanban.models.activity import TaskActivity
from core.modules.kanban.models.label import Label
from core.modules.kanban.models.task import Status, Task
from core.modules.kanban.services.automation import AutomationService
from core.modules.kanban.services.digest import DigestService
from core.modules.kanban.tests.helpers import API, KanbanTestCase, client_for
from core.modules.notifications.models.notification import Notification
from core.modules.user_settings.models.user_settings import UserSettings
from core.tasks.digest import send_digests


class AutomationTests(KanbanTestCase):
    def rule(self, sector, client=None, **data):
        return (client or self.client).post(
            f"{API}sectors/{sector}/automations/",
            {"name": "Regra", **data},
            format="json",
        )

    def test_moved_to_done_assigns_and_records_the_rule(self):
        sector = self.make_sector()
        self.share_sector(sector, self.member, "editor")
        done = self.status_ids(sector)["Concluído"]
        res = self.rule(
            sector,
            trigger="moved",
            trigger_value=done,
            action="assign",
            action_value=str(self.member.id),
        )
        self.assertEqual(res.status_code, 201, res.content)
        task = self.make_task(sector)
        self.client.post(f"{API}tasks/{task['id']}/move/", {"status": done})
        self.assertEqual(Task.objects.get(pk=task["id"]).assignee, self.member)
        last = TaskActivity.objects.filter(task_id=task["id"]).first()
        self.assertEqual(last.changes["automation"], [None, "Regra"])
        self.assertEqual(
            self.client.get(f"{API}sectors/{sector}/automations/").json()[0][
                "run_count"
            ],
            1,
        )

    def test_created_and_priority_rules(self):
        sector = self.make_sector()
        label = Label.objects.create(sector_id=sector, name="Triagem")
        self.rule(sector, trigger="created", action="label", action_value=str(label.id))
        self.rule(
            sector,
            trigger="priority",
            trigger_value="urgent",
            action="due",
            action_value="0",
        )
        task = self.make_task(sector)
        self.assertEqual(
            list(Task.objects.get(pk=task["id"]).labels.values_list("name", flat=True)),
            ["Triagem"],
        )
        self.client.patch(f"{API}tasks/{task['id']}/", {"priority": "urgent"})
        self.assertEqual(Task.objects.get(pk=task["id"]).due_date, timezone.localdate())

    def test_rules_do_not_chain(self):
        sector = self.make_sector()
        ids = self.status_ids(sector)
        # created -> move to "Em andamento"; moved to "Em andamento" -> move to done
        self.rule(
            sector, trigger="created", action="move", action_value=ids["Em andamento"]
        )
        self.rule(
            sector,
            trigger="moved",
            trigger_value=ids["Em andamento"],
            action="move",
            action_value=ids["Concluído"],
        )
        task = self.make_task(sector)
        self.assertEqual(
            str(Task.objects.get(pk=task["id"]).status_id), ids["Em andamento"]
        )

    def test_values_must_belong_to_the_project(self):
        sector, other = self.make_sector(), self.make_sector()
        foreign = self.status_ids(other)["Concluído"]
        res = self.rule(sector, trigger="created", action="move", action_value=foreign)
        self.assertEqual(res.status_code, 400)
        outsider = User.objects.create_user(email="x@b.com", password="x12345678!")
        res = self.rule(
            sector, trigger="created", action="assign", action_value=str(outsider.id)
        )
        self.assertEqual(res.status_code, 400)
        res = self.rule(
            sector, trigger="priority", trigger_value="huge", action="archive"
        )
        self.assertEqual(res.status_code, 400)

    def test_only_managers_write_rules(self):
        sector = self.make_sector()
        self.share_sector(sector, self.member, "editor")
        res = self.rule(sector, self.member_client, trigger="created", action="archive")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(
            self.member_client.get(f"{API}sectors/{sector}/automations/").status_code,
            200,
        )

    def test_overdue_rule_runs_once_per_task(self):
        sector = self.make_sector()
        self.share_sector(sector, self.member, "editor")
        self.rule(
            sector, trigger="overdue", action="notify", action_value=str(self.member.id)
        )
        yesterday = timezone.localdate() - timedelta(days=1)
        self.make_task(sector, due_date=yesterday.isoformat())
        self.assertEqual(AutomationService.run_overdue(), 1)
        self.assertEqual(AutomationService.run_overdue(), 0)
        self.assertEqual(
            Notification.objects.filter(
                user=self.member, data__event="automation.notice"
            ).count(),
            1,
        )


TRELLO = {
    "lists": [{"id": "l1", "name": "Backlog"}, {"id": "l2", "name": "Concluído"}],
    "cards": [
        {
            "id": "c1",
            "name": "Criar landing",
            "desc": "Página inicial",
            "idList": "l1",
            "due": "2026-12-01T12:00:00.000Z",
            "labels": [{"name": "Site", "color": "green"}],
        },
        {"id": "c2", "name": "Logo", "idList": "l2", "labels": []},
        {"id": "c3", "name": "Arquivado", "idList": "l1", "closed": True},
    ],
    "checklists": [
        {"idCard": "c1", "checkItems": [{"name": "Hero"}, {"name": "Rodapé"}]}
    ],
}
JIRA = (
    "Summary,Issue key,Status,Priority,Due Date,Labels,Labels,Description\n"
    "Corrigir login,APP-1,In Progress,Highest,05/Dec/26 10:00 AM,auth,bug,Erro 500\n"
    "Novo relatório,APP-2,Done,Low,,,,\n"
)
ASANA = (
    "Task ID,Name,Section/Column,Assignee Email,Due Date,Tags,Notes,Completed At\n"
    "1,Revisar contrato,A fazer,member@a.com,2026-12-10,jurídico,Ver cláusula 3,\n"
)


class ImportTests(KanbanTestCase):
    def upload(self, sector, source, content, name, dry_run=True, client=None):
        raw = content.encode() if isinstance(content, str) else content
        return (client or self.client).post(
            f"{API}sectors/{sector}/import/",
            {
                "source": source,
                "dry_run": "true" if dry_run else "false",
                "file": SimpleUploadedFile(name, raw),
            },
            format="multipart",
        )

    def test_trello_preview_then_import(self):
        sector = self.make_sector()
        raw = json.dumps(TRELLO)
        preview = self.upload(sector, "trello", raw, "board.json").json()
        self.assertEqual(preview["total"], 2)
        self.assertEqual(preview["created"], 0)
        self.assertEqual(preview["new_columns"], ["Backlog"])
        self.assertEqual(Task.objects.filter(sector_id=sector).count(), 0)

        result = self.upload(sector, "trello", raw, "board.json", dry_run=False).json()
        self.assertEqual(result["created"], 2)
        landing = Task.objects.get(sector_id=sector, title="Criar landing")
        self.assertEqual(landing.status.name, "Backlog")
        self.assertEqual(str(landing.due_date), "2026-12-01")
        self.assertEqual(landing.checklist_items.count(), 2)
        self.assertEqual(list(landing.labels.values_list("name", flat=True)), ["Site"])
        logo = Task.objects.get(sector_id=sector, title="Logo")
        self.assertIsNotNone(logo.completed_at)
        self.assertEqual(
            sorted(
                Task.objects.filter(sector_id=sector).values_list("sequence", flat=True)
            ),
            [1, 2],
        )

    def test_jira_and_asana_csv(self):
        sector = self.make_sector()
        self.share_sector(sector, self.member, "editor")
        self.upload(sector, "jira", JIRA, "jira.csv", dry_run=False)
        bug = Task.objects.get(sector_id=sector, title="Corrigir login")
        self.assertEqual(bug.priority, "urgent")
        self.assertEqual(str(bug.due_date), "2026-12-05")
        self.assertEqual(
            sorted(bug.labels.values_list("name", flat=True)), ["auth", "bug"]
        )
        self.assertEqual(
            Status.objects.get(sector_id=sector, name="Done").category, "done"
        )

        result = self.upload(sector, "asana", ASANA, "asana.csv", dry_run=False).json()
        self.assertEqual(result["assigned"], 1)
        task = Task.objects.get(sector_id=sector, title="Revisar contrato")
        self.assertEqual(task.assignee, self.member)
        self.assertEqual(task.status.name, "A fazer")

    def test_bad_files_and_viewers(self):
        sector = self.make_sector()
        self.assertEqual(
            self.upload(sector, "trello", "not json", "a.json").status_code, 400
        )
        self.assertEqual(
            self.upload(sector, "jira", "foo,bar\n1,2\n", "a.csv").status_code, 400
        )
        self.share_sector(sector, self.member, "viewer")
        res = self.upload(sector, "jira", JIRA, "jira.csv", client=self.member_client)
        self.assertEqual(res.status_code, 403)


class PublicLinkTests(KanbanTestCase):
    def test_link_shows_board_without_people_and_can_be_revoked(self):
        sector = self.make_sector()
        self.make_task(sector, title="Pública", description="segredo interno")
        self.assertEqual(
            self.member_client.post(f"{API}sectors/{sector}/public-link/").status_code,
            404,
        )
        token = self.client.post(f"{API}sectors/{sector}/public-link/").json()["token"]
        self.assertEqual(
            self.client.post(f"{API}sectors/{sector}/public-link/").json()["token"],
            token,
        )
        anon = APIClient()
        board = anon.get(f"{API}public/projects/{token}/").json()
        self.assertEqual(board["tasks"][0]["title"], "Pública")
        self.assertNotIn("segredo", json.dumps(board))
        self.assertNotIn("owner@a.com", json.dumps(board))
        self.client.delete(f"{API}sectors/{sector}/public-link/")
        self.assertEqual(anon.get(f"{API}public/projects/{token}/").status_code, 404)
        self.assertEqual(anon.get(f"{API}public/projects/qualquer/").status_code, 404)


class GuestTests(KanbanTestCase):
    def test_guest_sees_only_projects_they_were_added_to(self):
        open_sector = self.make_sector(name="Aberto")
        shared = self.make_sector(name="Cliente", is_private=True)
        guest = self.add_org_member("guest@b.com", "guest")
        guest_client = client_for(guest)
        self.share_sector(shared, guest, "editor")

        listed = guest_client.get(f"{API}organizations/{self.org.id}/sectors/").json()
        names = [row["name"] for row in listed.get("results", listed)]
        self.assertEqual(names, ["Cliente"])
        self.assertEqual(
            guest_client.get(f"{API}sectors/{open_sector}/").status_code, 404
        )
        self.assertEqual(guest_client.get(f"{API}sectors/{shared}/").status_code, 200)
        self.make_task(shared, client=guest_client)
        # organization-wide screens stay closed; the organization itself opens
        self.assertEqual(
            guest_client.get(f"{API}organizations/{self.org.id}/members/").status_code,
            404,
        )
        self.assertEqual(
            guest_client.get(f"{API}organizations/{self.org.id}/").status_code, 200
        )

        people = self.client.get(f"{API}sectors/{open_sector}/people/").json()
        people = people.get("results", people) if isinstance(people, dict) else people
        self.assertNotIn(str(guest.id), json.dumps(people))

    def test_guest_invite_needs_a_project(self):
        res = self.client.post(
            f"{API}organizations/{self.org.id}/invitations/",
            {"email": "ext@b.com", "role": "guest"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class DigestTests(KanbanTestCase):
    def test_daily_digest_only_when_there_is_something(self):
        sector = self.make_sector()
        UserSettings.objects.update_or_create(
            user=self.owner, defaults={"email_daily_digest": True}
        )
        self.assertEqual(send_digests(), 0)
        yesterday = timezone.localdate() - timedelta(days=1)
        self.make_task(
            sector,
            title="Atrasada",
            assignee=str(self.owner.id),
            due_date=yesterday.isoformat(),
        )
        self.assertEqual(send_digests() >= 1, True)
        self.assertIn("Atrasada", mail.outbox[-1].body)
        self.assertEqual(mail.outbox[-1].to, ["owner@a.com"])

    def test_removed_people_do_not_hear_about_the_project(self):
        sector = self.make_sector(is_private=True)
        self.share_sector(sector, self.member, "editor")
        self.make_task(
            sector,
            assignee=str(self.member.id),
            due_date=timezone.localdate().isoformat(),
        )
        self.assertIsNotNone(DigestService.content(self.member, weekly=False))
        members = self.client.get(f"{API}sectors/{sector}/members/").json()
        members = (
            members.get("results", members) if isinstance(members, dict) else members
        )
        mine = next(m for m in members if m["user_id"] == str(self.member.id))
        self.client.delete(f"{API}sectors/{sector}/members/{mine['id']}/")
        self.assertIsNone(DigestService.content(self.member, weekly=False))
