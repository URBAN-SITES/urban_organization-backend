from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile

from core.modules.chat import presence
from core.modules.chat.models.chat import ChatMessage
from core.modules.chat.services.chat import ChatService
from core.modules.chat.tests.test_chat import (
    API,
    PUSH,
    ChatTestCase,
    client_for,
    make_user,
)
from core.modules.kanban.models.sector import Sector, SectorMember
from core.modules.kanban.services.sector import SectorService
from core.modules.kanban.services.task import TaskService
from core.modules.notifications.models.notification import Notification
from core.modules.uploads.models.attachment import Attachment

UPLOAD = "core.modules.uploads.services.attachment.UploadService.upload"
DELETE = "core.modules.uploads.services.attachment.UploadService.delete"


def fake_upload(file, folder="uploads"):
    return {"url": f"https://cdn/{file.name}", "public_id": f"{folder}/{file.name}"}


class SectorChannelTests(ChatTestCase):
    def make_sector(self, user=None, **data):
        return SectorService.create(
            user or self.owner, self.org.id, **{"name": "Marketing", **data}
        )

    def sector_channel(self, user):
        found = [c for c in self.channels(user) if c["kind"] == "sector"]
        return found[0] if found else None

    def test_channel_follows_sector_access(self):
        sector = self.make_sector()  # private
        self.assertIsNone(self.sector_channel(self.ana))
        SectorMember.objects.create(sector=sector, user=self.ana, role="viewer")
        channel = self.sector_channel(self.ana)
        self.assertEqual(
            (channel["name"], channel["sector_id"]), ("Marketing", str(sector.id))
        )
        self.assertEqual(self.say(self.ana, channel["id"], "hello").status_code, 201)
        self.assertEqual(self.say(self.bob, channel["id"]).status_code, 404)
        # org owner is an implicit manager, so he sees it too
        self.assertIsNotNone(self.sector_channel(self.owner))
        # losing the participation closes the channel
        SectorMember.objects.filter(user=self.ana).delete()
        self.assertEqual(self.say(self.ana, channel["id"]).status_code, 404)

    def test_public_sector_is_open_to_the_whole_organization(self):
        self.make_sector(is_private=False)
        for user in (self.ana, self.bob):
            self.assertIsNotNone(self.sector_channel(user))

    def test_broadcast_reaches_only_participants_and_member_count(self):
        sector = self.make_sector()
        SectorMember.objects.create(sector=sector, user=self.ana, role="editor")
        channel = self.sector_channel(self.ana)
        self.assertEqual(channel["member_count"], 2)  # owner (implicit) + Ana
        with patch(PUSH) as push, self.captureOnCommitCallbacks(execute=True):
            self.say(self.ana, channel["id"], "hi")
        users = {call.args[0] for call in push.call_args_list}
        self.assertEqual(users, {self.owner.id, self.ana.id})

    def test_rename_and_delete_follow_the_sector(self):
        sector = self.make_sector(is_private=False)
        channel = self.sector_channel(self.ana)
        SectorService.update(self.owner, sector.id, {"name": "Growth"})
        self.assertEqual(self.sector_channel(self.ana)["name"], "Growth")
        SectorService.delete(self.owner, sector.id)
        self.assertIsNone(self.sector_channel(self.ana))
        self.assertEqual(self.say(self.ana, channel["id"]).status_code, 404)
        self.assertFalse(Sector.objects.get(id=sector.id).is_active)


class ChannelListTests(ChatTestCase):
    def test_last_message_and_ordering(self):
        general = self.general(self.ana)
        self.assertIsNone(general["last_message"])
        self.assertEqual(general["member_count"], 3)
        self.make_team(self.ana)
        team = self.team_channel(self.ana)
        self.say(self.ana, general["id"], "first")
        self.say(self.ana, team["id"], "latest")
        channels = self.channels(self.ana)
        self.assertEqual(channels[0]["id"], team["id"])  # most recent activity first
        self.assertEqual(channels[0]["last_message"]["content"], "latest")
        self.assertEqual(channels[0]["last_message"]["author_name"], "Ana")
        self.assertFalse(channels[0]["last_message"]["has_attachments"])

    def test_deleted_message_is_not_the_preview(self):
        general = self.general(self.ana)["id"]
        self.say(self.ana, general, "keep")
        gone = self.say(self.ana, general, "remove me").json()
        self.clients[self.ana].delete(f"{API}chat/messages/{gone['id']}/")
        self.assertEqual(self.general(self.bob)["last_message"]["content"], "keep")


class MentionAndTaskTests(ChatTestCase):
    def setUp(self):
        super().setUp()
        self.general_id = self.general(self.ana)["id"]

    def test_mention_notifies_and_is_serialized(self):
        res = self.say(
            self.ana, self.general_id, "hi @Bob", mentions=[str(self.bob.id)]
        )
        self.assertEqual(
            res.json()["mentions"], [{"id": str(self.bob.id), "name": "Bob"}]
        )
        note = Notification.objects.get(user=self.bob)
        self.assertEqual(note.data["channel_id"], self.general_id)
        self.assertEqual(note.message, "hi @Bob")

    def test_every_message_notifies_channel_members_except_the_author(self):
        self.say(self.ana, self.general_id, "hello everyone")
        notifications = Notification.objects.filter().order_by("user_id")
        self.assertEqual(
            list(notifications.values_list("user_id", flat=True)),
            sorted([self.owner.id, self.bob.id]),
        )
        self.assertEqual(notifications[0].message, "hello everyone")
        self.assertEqual(notifications[0].data["channel_id"], self.general_id)

    def test_direct_message_notifies_only_the_other_participant(self):
        direct = ChatService.open_direct(self.ana, self.org.id, self.bob.id)["id"]
        self.say(self.ana, direct, "private")
        self.assertEqual(
            list(Notification.objects.values_list("user_id", flat=True)), [self.bob.id]
        )

    def test_only_readers_are_mentioned_and_never_the_author(self):
        self.make_team(self.ana)
        team = self.team_channel(self.ana)["id"]
        res = self.say(
            self.ana, team, "psst", mentions=[str(self.bob.id), str(self.ana.id)]
        )
        self.assertEqual(res.json()["mentions"], [])  # Bob is not in the team
        self.assertEqual(Notification.objects.count(), 0)

    def test_cite_a_task_shows_a_card(self):
        sector = SectorService.create(
            self.owner, self.org.id, name="Dev", is_private=False
        )
        SectorMember.objects.create(sector=sector, user=self.ana, role="editor")
        task = TaskService.create(self.owner, sector.id, {"title": "Landing page"})
        res = self.say(self.ana, self.general_id, "see #", task=str(task.id))
        self.assertEqual(res.status_code, 201, res.content)
        card = res.json()["task"]
        self.assertEqual(
            (card["title"], card["status"], card["completed"]),
            ("Landing page", "A fazer", False),
        )
        listed = self.clients[self.bob].get(
            f"{API}chat/channels/{self.general_id}/messages/"
        )
        self.assertEqual(listed.json()["results"][0]["task"]["id"], str(task.id))

    def test_cannot_cite_a_task_you_cannot_see(self):
        sector = SectorService.create(self.owner, self.org.id, name="Secret")  # private
        task = TaskService.create(self.owner, sector.id, {"title": "Hidden"})
        res = self.say(self.ana, self.general_id, "x", task=str(task.id))
        self.assertEqual(res.status_code, 400)
        self.assertEqual(ChatMessage.objects.count(), 0)


class AttachmentTests(ChatTestCase):
    def setUp(self):
        super().setUp()
        self.general_id = self.general(self.ana)["id"]
        self.url = f"{API}chat/channels/{self.general_id}/messages/"

    def post(self, files, **data):
        return self.clients[self.ana].post(
            self.url, {**data, "files": files}, format="multipart"
        )

    def pdf(self, name="ata.pdf", size=100):
        return SimpleUploadedFile(name, b"x" * size, content_type="application/pdf")

    @patch(UPLOAD, side_effect=fake_upload)
    def test_message_with_files(self, upload):
        res = self.post(
            [self.pdf("ata.pdf", 412), self.pdf("plan.pdf")], content="docs"
        )
        self.assertEqual(res.status_code, 201, res.content)
        files = res.json()["attachments"]
        self.assertEqual(
            sorted((f["file_name"], f["mime_type"]) for f in files),
            [("ata.pdf", "application/pdf"), ("plan.pdf", "application/pdf")],
        )
        self.assertEqual(Attachment.objects.count(), 2)
        self.assertEqual(Attachment.objects.get(file_name="ata.pdf").size_bytes, 412)
        listed = self.clients[self.bob].get(self.url).json()["results"][0]
        self.assertEqual(len(listed["attachments"]), 2)
        self.assertTrue(self.general(self.bob)["last_message"]["has_attachments"])
        self.assertEqual(upload.call_count, 2)

    @patch(UPLOAD, side_effect=fake_upload)
    def test_file_only_message_is_allowed_but_empty_is_not(self, _upload):
        self.assertEqual(self.post([self.pdf()]).status_code, 201)
        self.assertEqual(self.post([], content="").status_code, 400)

    @patch(UPLOAD, side_effect=fake_upload)
    def test_limits(self, upload):
        too_many = [self.pdf(f"{i}.pdf") for i in range(6)]
        self.assertEqual(self.post(too_many, content="x").status_code, 400)
        big = self.pdf("big.pdf", 10 * 1024 * 1024 + 1)
        self.assertEqual(self.post([big], content="x").status_code, 400)
        upload.assert_not_called()
        self.assertEqual(ChatMessage.objects.count(), 0)

    @patch(DELETE)
    @patch(UPLOAD)
    def test_failed_upload_leaves_nothing_behind(self, upload, delete):
        folder = f"chat/{self.org.id}"
        upload.side_effect = [
            fake_upload(self.pdf("a.pdf"), folder=folder),
            RuntimeError("boom"),
        ]
        with self.assertRaises(RuntimeError):
            self.post([self.pdf("a.pdf"), self.pdf("b.pdf")], content="x")
        delete.assert_called_once_with("chat/%s/a.pdf" % self.org.id)
        self.assertEqual(
            (ChatMessage.objects.count(), Attachment.objects.count()), (0, 0)
        )

    @patch(DELETE)
    @patch(UPLOAD, side_effect=fake_upload)
    def test_deleting_the_message_removes_its_files(self, _upload, delete):
        message = self.post([self.pdf("ata.pdf")], content="x").json()
        res = self.clients[self.ana].delete(f"{API}chat/messages/{message['id']}/")
        self.assertEqual(res.status_code, 204)
        self.assertEqual(Attachment.objects.count(), 0)
        delete.assert_called_once()


class PresenceTests(ChatTestCase):
    def tearDown(self):
        for user in (self.owner, self.ana, self.bob):
            presence.mark_offline(user.id)
            presence.mark_offline(user.id)

    def test_counter_semantics(self):
        presence.mark_online(self.ana.id)
        presence.mark_online(self.ana.id)  # two tabs
        presence.mark_offline(self.ana.id)
        self.assertTrue(presence.is_online(self.ana.id))
        presence.mark_offline(self.ana.id)
        self.assertFalse(presence.is_online(self.ana.id))
        presence.mark_offline(self.ana.id)  # never goes negative
        self.assertFalse(presence.is_online(self.ana.id))

    def test_endpoint_and_direct_channel_flag(self):
        presence.mark_online(self.bob.id)
        url = f"{API}organizations/{self.org.id}/chat/presence/"
        online = self.clients[self.ana].get(url).json()["online"]
        self.assertEqual(online, [str(self.bob.id)])
        direct = self.clients[self.ana].post(
            f"{API}organizations/{self.org.id}/chat/direct/",
            {"user_id": str(self.bob.id)},
        )
        self.assertTrue(direct.json()["online"])
        presence.mark_offline(self.bob.id)
        self.assertFalse(
            next(c for c in self.channels(self.ana) if c["kind"] == "direct")["online"]
        )
        self.assertIsNone(self.general(self.ana)["online"])
        stranger = client_for(make_user("s@a.com"))
        self.assertEqual(stranger.get(url).status_code, 404)

    def test_typing_recipients(self):
        general = self.general(self.ana)["id"]
        recipients = ChatService.typing_recipients(self.ana, general)
        self.assertCountEqual(recipients, [self.owner.id, self.bob.id])
        stranger = make_user("s@a.com")
        self.assertEqual(ChatService.typing_recipients(stranger, general), [])
        self.assertEqual(ChatService.typing_recipients(self.ana, "not-a-uuid"), [])
