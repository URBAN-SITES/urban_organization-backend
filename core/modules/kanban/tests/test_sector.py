from datetime import timedelta

from django.utils import timezone

from core.modules.kanban.models.sector import Sector, SectorMember
from core.modules.kanban.models.task import Status
from core.modules.kanban.services.sector import SectorService
from core.modules.kanban.tests.helpers import (
    API,
    KanbanTestCase,
    client_for,
    make_user,
)
from core.modules.organizations.services.organization import OrganizationService
from core.modules.teams.services.team import TeamService


class SectorTests(KanbanTestCase):
    def test_create_adds_manager_and_default_columns(self):
        sector_id = self.make_sector()
        member = SectorMember.objects.get(sector_id=sector_id)
        self.assertEqual((member.user, member.role), (self.owner, "manager"))
        columns = Status.objects.filter(sector_id=sector_id)
        self.assertEqual(
            [(s.name, s.category, s.position) for s in columns],
            [
                ("A fazer", "todo", 0),
                ("Em andamento", "in_progress", 1),
                ("Concluído", "done", 2),
            ],
        )

    def test_org_viewer_cannot_create_but_member_can(self):
        viewer = self.add_org_member("v@a.com", "viewer")
        url = f"{API}organizations/{self.org.id}/sectors/"
        self.assertEqual(client_for(viewer).post(url, {"name": "X"}).status_code, 403)
        self.make_sector(self.member_client)

    def test_private_sector_is_hidden_from_non_participants(self):
        sector_id = self.make_sector(self.member_client)  # private by default
        list_url = f"{API}organizations/{self.org.id}/sectors/"
        other = self.add_org_member("o@a.com")
        other_client = client_for(other)
        self.assertEqual(
            other_client.get(f"{API}sectors/{sector_id}/").status_code, 404
        )
        self.assertEqual(other_client.get(list_url).json()["results"], [])
        # org owner is an implicit manager and sees everything
        res = self.client.get(f"{API}sectors/{sector_id}/")
        self.assertEqual(res.json()["my_role"], "manager")
        self.assertEqual(len(self.client.get(list_url).json()["results"]), 1)

    def test_public_sector_gives_org_members_viewer_access(self):
        sector_id = self.make_sector(is_private=False)
        res = self.member_client.get(f"{API}sectors/{sector_id}/")
        self.assertEqual(res.json()["my_role"], "viewer")
        res = self.member_client.post(
            f"{API}sectors/{sector_id}/tasks/", {"title": "x"}
        )
        self.assertEqual(res.status_code, 403)

    def test_org_admin_is_implicit_manager(self):
        admin = self.add_org_member("adm@a.com", "admin")
        sector_id = self.make_sector(self.member_client)
        res = client_for(admin).patch(f"{API}sectors/{sector_id}/", {"name": "Renamed"})
        self.assertEqual(res.json()["name"], "Renamed")

    def test_effective_role_takes_the_highest_source(self):
        sector_id = self.make_sector(is_private=False)
        sector = Sector.objects.get(id=sector_id)
        self.assertEqual(SectorService.effective_role(self.member, sector), "viewer")
        self.share_sector(sector_id, self.member, "editor")
        self.assertEqual(SectorService.effective_role(self.member, sector), "editor")
        team = TeamService.create(self.owner, self.org.id, name="Ops")
        TeamService.add_member(
            self.owner, self.org.id, team.id, self.member.id, "member"
        )
        self.client.post(
            f"{API}sectors/{sector_id}/teams/",
            {"team_id": str(team.id), "role": "manager"},
        )
        self.assertEqual(SectorService.effective_role(self.member, sector), "manager")

    def test_team_link_gives_access_and_can_be_removed(self):
        sector_id = self.make_sector()
        team = TeamService.create(self.owner, self.org.id, name="Ops")
        TeamService.add_member(
            self.owner, self.org.id, team.id, self.member.id, "member"
        )
        self.assertEqual(
            self.member_client.get(f"{API}sectors/{sector_id}/").status_code, 404
        )
        url = f"{API}sectors/{sector_id}/teams/"
        res = self.client.post(url, {"team_id": str(team.id)})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(
            self.client.post(url, {"team_id": str(team.id)}).status_code, 400
        )
        self.assertEqual(
            self.member_client.get(f"{API}sectors/{sector_id}/").json()["my_role"],
            "editor",
        )
        self.client.delete(f"{url}{res.json()['id']}/")
        self.assertEqual(
            self.member_client.get(f"{API}sectors/{sector_id}/").status_code, 404
        )

    def test_team_from_another_organization_is_rejected(self):
        sector_id = self.make_sector()
        stranger = make_user("s@a.com")
        other_org = OrganizationService.create(stranger, name="Other")
        team = TeamService.create(stranger, other_org.id, name="Alien")
        res = self.client.post(
            f"{API}sectors/{sector_id}/teams/", {"team_id": str(team.id)}
        )
        self.assertEqual(res.status_code, 400)

    def test_losing_organization_membership_revokes_sector_access(self):
        sector_id = self.make_sector()
        self.share_sector(sector_id, self.member, "manager")
        self.assertEqual(
            self.member_client.get(f"{API}sectors/{sector_id}/").status_code, 200
        )
        self.org.members.filter(user=self.member).delete()
        self.assertEqual(
            self.member_client.get(f"{API}sectors/{sector_id}/").status_code, 404
        )

    def test_participant_management_rules(self):
        sector_id = self.make_sector()
        url = f"{API}sectors/{sector_id}/members/"
        outsider = make_user("out@a.com")
        res = self.client.post(url, {"user_id": str(outsider.id)})
        self.assertEqual(res.status_code, 400)
        self.share_sector(sector_id, self.member, "editor")
        res = self.client.post(url, {"user_id": str(self.member.id)})
        self.assertEqual(res.status_code, 400)
        # an editor cannot manage participants
        res = self.member_client.post(url, {"user_id": str(self.owner.id)})
        self.assertEqual(res.status_code, 403)
        member_row = SectorMember.objects.get(user=self.member)
        res = self.client.patch(f"{url}{member_row.id}/", {"role": "viewer"})
        self.assertEqual(res.json()["role"], "viewer")
        # but anyone can leave
        res = self.member_client.delete(f"{url}{member_row.id}/")
        self.assertEqual(res.status_code, 204)
        self.assertEqual(len(self.client.get(url).json()["results"]), 1)

    def test_update_and_delete_need_manager_and_delete_is_soft(self):
        sector_id = self.make_sector()
        self.share_sector(sector_id, self.member, "editor")
        detail = f"{API}sectors/{sector_id}/"
        self.assertEqual(
            self.member_client.patch(detail, {"name": "x"}).status_code, 403
        )
        self.assertEqual(self.member_client.delete(detail).status_code, 403)
        self.assertEqual(self.client.delete(detail).status_code, 204)
        self.assertFalse(Sector.objects.get(id=sector_id).is_active)
        self.assertEqual(self.client.get(detail).status_code, 404)

    def test_progress(self):
        sector_id = self.make_sector()
        empty = self.client.get(f"{API}sectors/{sector_id}/progress/").json()
        self.assertEqual(
            empty, {"total": 0, "completed": 0, "overdue": 0, "percent": 0.0}
        )
        done = self.status_ids(sector_id)["Concluído"]
        yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
        self.make_task(sector_id, due_date=yesterday)
        self.make_task(sector_id, status=done, due_date=yesterday)
        self.make_task(sector_id)
        self.make_task(sector_id, status=done)
        progress = self.client.get(f"{API}sectors/{sector_id}/progress/").json()
        self.assertEqual(
            progress, {"total": 4, "completed": 2, "overdue": 1, "percent": 50.0}
        )
