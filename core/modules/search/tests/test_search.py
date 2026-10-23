from django.test import TestCase
from rest_framework.test import APIClient

from core.models.user import User
from core.modules.chat.models.chat import ChatMessage
from core.modules.chat.services.chat import ChatService
from core.modules.kanban.models.sector import SectorMember
from core.modules.kanban.services.sector import SectorService
from core.modules.kanban.services.task import TaskService
from core.modules.organizations.models.organization import OrganizationMember
from core.modules.organizations.services.organization import OrganizationService
from core.modules.teams.services.team import TeamService
from core.modules.uploads.models.attachment import Attachment

API = "/api/v1/"


def make_user(email, name):
    return User.objects.create_user(email=email, password="x12345678!", name=name)


class SearchTests(TestCase):
    def setUp(self):
        self.owner = make_user("owner@a.com", "Owner")
        self.org = OrganizationService.create(self.owner, name="Acme")
        self.ana = self.join("ana@a.com", "Camila Alves")
        self.bob = self.join("bob@a.com", "Bob")
        self.url = f"{API}organizations/{self.org.id}/search/"

    def join(self, email, name):
        user = make_user(email, name)
        OrganizationMember.objects.create(organization=self.org, user=user)
        return user

    def search(self, user, query):
        client = APIClient()
        client.force_authenticate(user)
        return client.get(self.url, {"q": query})

    def file(self, name, **target):
        return Attachment.objects.create(
            organization=self.org,
            uploaded_by=self.owner,
            url=f"https://cdn/{name}",
            storage_key=f"k/{name}",
            file_name=name,
            mime_type="application/pdf",
            size_bytes=10,
            **target,
        )

    def test_people_match_name_or_email(self):
        res = self.search(self.bob, "camila").json()
        self.assertEqual([p["name"] for p in res["people"]], ["Camila Alves"])
        res = self.search(self.bob, "bob@a").json()
        self.assertEqual([p["email"] for p in res["people"]], ["bob@a.com"])

    def test_tasks_respect_sector_visibility(self):
        public = SectorService.create(
            self.owner, self.org.id, name="Open", is_private=False
        )
        private = SectorService.create(self.owner, self.org.id, name="Secret")
        TaskService.create(self.owner, public.id, {"title": "Landing page"})
        TaskService.create(self.owner, private.id, {"title": "Landing budget"})
        titles = [t["title"] for t in self.search(self.bob, "landing").json()["tasks"]]
        self.assertEqual(titles, ["Landing page"])
        SectorMember.objects.create(sector=private, user=self.bob, role="viewer")
        titles = [t["title"] for t in self.search(self.bob, "landing").json()["tasks"]]
        self.assertCountEqual(titles, ["Landing page", "Landing budget"])
        card = self.search(self.owner, "page").json()["tasks"][0]
        self.assertEqual((card["sector_name"], card["status"]), ("Open", "To do"))

    def test_files_respect_where_they_live(self):
        public = SectorService.create(
            self.owner, self.org.id, name="Open", is_private=False
        )
        private = SectorService.create(self.owner, self.org.id, name="Secret")
        self.file("ata-org.pdf")  # organization document
        self.file("ata-open.pdf", sector=public)
        self.file("ata-secret.pdf", sector=private)
        team = TeamService.create(self.owner, self.org.id, name="Ops")
        TeamService.add_member(self.owner, self.org.id, team.id, self.ana.id, "member")
        channel = next(
            c
            for c in ChatService.list_channels(self.ana, self.org.id)
            if c["kind"] == "team"
        )
        message = ChatMessage.objects.create(
            channel_id=channel["id"], author=self.ana, content="x"
        )
        self.file("ata-chat.pdf", message=message)

        def names(user):
            return {f["file_name"] for f in self.search(user, "ata").json()["files"]}

        self.assertEqual(names(self.bob), {"ata-org.pdf", "ata-open.pdf"})
        self.assertEqual(
            names(self.ana), {"ata-org.pdf", "ata-open.pdf", "ata-chat.pdf"}
        )
        self.assertEqual(
            names(self.owner),
            {"ata-org.pdf", "ata-open.pdf", "ata-secret.pdf", "ata-chat.pdf"},
        )

    def test_validation_and_isolation(self):
        self.assertEqual(self.search(self.bob, "a").status_code, 400)
        self.assertEqual(self.search(self.bob, "  ").status_code, 400)
        stranger = make_user("s@a.com", "Stranger")
        self.assertEqual(self.search(stranger, "bob").status_code, 404)
        client = APIClient()
        self.assertEqual(client.get(self.url, {"q": "bob"}).status_code, 401)
