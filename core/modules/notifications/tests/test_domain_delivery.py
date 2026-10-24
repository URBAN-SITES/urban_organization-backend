from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from django.db import transaction
from django.test import TestCase, override_settings
from rest_framework.exceptions import ValidationError

from core.models.user import User
from core.modules.chat.models.chat import ChatChannel, ChatMessage
from core.modules.chat.services.chat import ChatService
from core.modules.invitations.models.invite import OrganizationInvite
from core.modules.invitations.services.invite import InviteService
from core.modules.kanban.models.sector import SectorMember
from core.modules.kanban.models.task import Comment, Task
from core.modules.kanban.services.item import CommentService
from core.modules.kanban.services.sector import SectorService
from core.modules.kanban.services.task import TaskService
from core.modules.notifications.models.notification import DeviceToken, Notification
from core.modules.notifications.services.notification import NotificationService
from core.modules.organizations.models.organization import OrganizationMember
from core.modules.organizations.services.organization import OrganizationService
from core.modules.user_settings.models.user_settings import UserSettings

SERVICE = "core.modules.notifications.services.notification"
EMAIL = "core.modules.invitations.services.invite.send_invite_email_task.delay"


@override_settings(FIREBASE_CREDENTIALS="fake.json", FRONTEND_URL="https://app.example")
class DomainDeliveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            email="owner@example.com", password=None, name="Owner"
        )
        cls.member = User.objects.create_user(
            email="member@example.com", password=None, name="Member"
        )
        cls.guest = User.objects.create_user(
            email="guest@example.com", password=None, name="Guest"
        )
        cls.org = OrganizationService.create(cls.owner, name="Workspace")
        cls.membership = OrganizationMember.objects.create(
            organization=cls.org, user=cls.member, role="member"
        )
        cls.sector = SectorService.create(cls.owner, cls.org.pk, name="Board")
        SectorMember.objects.create(sector=cls.sector, user=cls.member, role="editor")
        cls.todo = cls.sector.statuses.get(category="todo")
        cls.done = cls.sector.statuses.get(category="done")
        cls.task = Task.objects.create(
            sector=cls.sector,
            status=cls.todo,
            assignee=cls.member,
            owner=cls.owner,
            title="Deliver feature",
        )
        cls.channel = ChatChannel.objects.create(
            organization=cls.org, kind="organization", name="General"
        )
        for user in (cls.owner, cls.member, cls.guest):
            DeviceToken.objects.create(user=user, token=f"device-{user.pk}")

    def setUp(self):
        self.send = self.start_patch(f"{SERVICE}.messaging.send_each_for_multicast")
        self.send.return_value = MagicMock(
            responses=[MagicMock(exception=None)], success_count=1, failure_count=0
        )
        self.start_patch(f"{SERVICE}._firebase_app")
        self.socket = self.start_patch(f"{SERVICE}.send_to_user")
        self.start_patch("core.modules.chat.services.chat.send_to_user")
        self.email = self.start_patch(EMAIL)

    def start_patch(self, target):
        patcher = patch(target)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def assert_delivery(self, recipient, event):
        note = Notification.objects.get(user=recipient, data__event=event)
        message = self.send.call_args.args[0]
        self.assertEqual(message.tokens, [f"device-{recipient.pk}"])
        self.assertEqual(message.data["notification_id"], str(note.pk))
        self.assertEqual(message.data["event"], event)
        self.assertEqual(message.data["organization_id"], str(self.org.pk))
        self.assertTrue(all(isinstance(value, str) for value in message.data.values()))
        self.assertEqual(message.notification.title, note.title)
        self.assertEqual(
            message.webpush.fcm_options.link, "https://app.example/notificacoes"
        )
        self.assertEqual(self.socket.call_args.args[0], recipient.pk)
        self.assertEqual(self.socket.call_args.args[1]["type"], "notification.created")
        return note

    def test_task_assignment_and_reassignment_reach_fcm_after_commit(self):
        with self.captureOnCommitCallbacks(execute=True):
            task = TaskService.create(
                self.owner, self.sector.pk, {"title": "New", "assignee": self.member}
            )
            self.send.assert_not_called()
        self.assert_delivery(self.member, "task.assigned")
        with self.captureOnCommitCallbacks(execute=True):
            TaskService.update(self.member, task.pk, {"assignee": self.owner})
        self.assert_delivery(self.owner, "task.assigned")

    def test_comment_and_status_reach_fcm(self):
        with self.captureOnCommitCallbacks(execute=True):
            CommentService.create(self.owner, self.task.pk, "Review this")
        self.assert_delivery(self.member, "task.commented")
        with self.captureOnCommitCallbacks(execute=True):
            TaskService.move(self.owner, self.task.pk, self.done, None)
        self.assert_delivery(self.member, "task.status_changed")
        self.assertEqual(self.send.call_count, 2)

    def test_category_preferences_suppress_inbox_websocket_and_push(self):
        UserSettings.objects.create(
            user=self.member, app_comments=False, app_status=False
        )
        with self.captureOnCommitCallbacks(execute=True):
            CommentService.create(self.owner, self.task.pk, "Hidden category")
            TaskService.move(self.owner, self.task.pk, self.done, None)
        self.assertFalse(Notification.objects.exists())
        self.send.assert_not_called()
        self.socket.assert_not_called()
        self.assertTrue(Comment.objects.exists())

    def test_global_push_opt_out_preserves_inbox_and_websocket(self):
        UserSettings.objects.create(user=self.member, push_enabled=False)
        with self.captureOnCommitCallbacks(execute=True):
            TaskService.move(self.owner, self.task.pk, self.done, None)
        self.assertTrue(
            Notification.objects.filter(data__event="task.status_changed").exists()
        )
        self.socket.assert_called_once()
        self.send.assert_not_called()

    def test_reorder_and_self_actions_do_not_notify(self):
        with self.captureOnCommitCallbacks(execute=True):
            TaskService.move(self.owner, self.task.pk, self.todo, 0)
            TaskService.move(self.member, self.task.pk, self.done, None)
            CommentService.create(self.member, self.task.pk, "Own comment")
        self.assertFalse(Notification.objects.exists())
        self.send.assert_not_called()

    def test_former_assignee_cannot_receive_task_content(self):
        for removal in ("sector", "organization", "inactive"):
            with self.subTest(removal=removal), transaction.atomic():
                if removal == "sector":
                    SectorMember.objects.filter(
                        user=self.member, sector=self.sector
                    ).delete()
                elif removal == "organization":
                    OrganizationMember.objects.filter(pk=self.membership.pk).delete()
                else:
                    User.objects.filter(pk=self.member.pk).update(is_active=False)
                with self.captureOnCommitCallbacks(execute=True):
                    CommentService.create(self.owner, self.task.pk, "Private")
                    TaskService.move(self.owner, self.task.pk, self.done, None)
                self.assertFalse(Notification.objects.exists())
                self.send.assert_not_called()
                transaction.set_rollback(True)

    def test_chat_mentions_reach_only_accessible_active_non_authors(self):
        with self.captureOnCommitCallbacks(execute=True):
            ChatService.send(
                self.owner,
                self.channel.pk,
                "Hello",
                mention_ids=[
                    self.owner.pk,
                    self.member.pk,
                    self.member.pk,
                    self.guest.pk,
                ],
            )
            self.send.assert_not_called()
        self.assert_delivery(self.member, "chat.mentioned")
        self.assertEqual(Notification.objects.count(), 1)
        self.send.assert_called_once()

    def test_chat_message_without_mentions_does_not_create_push(self):
        with self.captureOnCommitCallbacks(execute=True):
            ChatService.send(self.owner, self.channel.pk, "Hello")
        self.assertTrue(ChatMessage.objects.exists())
        self.assertFalse(Notification.objects.exists())
        self.send.assert_not_called()

    def test_chat_message_and_notification_are_atomic(self):
        with patch.object(
            NotificationService, "notify", side_effect=RuntimeError("database")
        ):
            with (
                self.assertRaises(RuntimeError),
                self.captureOnCommitCallbacks(execute=True),
            ):
                ChatService.send(
                    self.owner, self.channel.pk, "Hello", mention_ids=[self.member.pk]
                )
        self.assertFalse(ChatMessage.objects.exists())
        self.send.assert_not_called()

    def test_member_add_role_change_remove_and_noop(self):
        with self.captureOnCommitCallbacks(execute=True):
            member = OrganizationService.add_member(
                self.owner, self.org.pk, self.guest.email, "member"
            )
        self.assert_delivery(self.guest, "organization.member_added")
        with self.captureOnCommitCallbacks(execute=True):
            OrganizationService.change_role(
                self.owner, self.org.pk, member.pk, "viewer"
            )
        self.assert_delivery(self.guest, "organization.role_changed")
        with self.captureOnCommitCallbacks(execute=True):
            OrganizationService.change_role(
                self.owner, self.org.pk, member.pk, "viewer"
            )
        self.assertEqual(self.send.call_count, 2)
        with self.captureOnCommitCallbacks(execute=True):
            OrganizationService.remove_member(self.owner, self.org.pk, member.pk)
        self.assert_delivery(self.guest, "organization.member_removed")
        self.assertFalse(OrganizationMember.objects.filter(pk=member.pk).exists())

    def test_leaving_organization_does_not_notify_self(self):
        with self.captureOnCommitCallbacks(execute=True):
            OrganizationService.remove_member(
                self.member, self.org.pk, self.membership.pk
            )
        self.assertFalse(Notification.objects.exists())
        self.send.assert_not_called()

    def test_invitation_and_acceptance_reach_registered_users_without_secret_token(
        self,
    ):
        with self.captureOnCommitCallbacks(execute=True):
            invite = InviteService.create(
                self.owner, self.org.pk, "GUEST@example.com", "member"
            )
        note = self.assert_delivery(self.guest, "organization.invited")
        link = self.email.call_args.args[2]
        token = parse_qs(urlparse(link).query)["token"][0]
        self.assertNotIn(token, str(note.data))
        self.assertNotIn(token, note.message)
        with self.captureOnCommitCallbacks(execute=True):
            InviteService.accept(self.guest, token)
        accepted = self.assert_delivery(self.owner, "organization.invite_accepted")
        self.assertEqual(accepted.data["invite_id"], str(invite.pk))
        self.assertEqual(self.send.call_count, 2)
        with self.assertRaises(ValidationError):
            InviteService.accept(self.guest, token)
        self.assertEqual(self.send.call_count, 2)

    def test_unknown_invitee_receives_email_only(self):
        with self.captureOnCommitCallbacks(execute=True):
            InviteService.create(
                self.owner, self.org.pk, "unknown@example.com", "member"
            )
        self.email.assert_called_once()
        self.assertFalse(Notification.objects.exists())
        self.send.assert_not_called()

    def test_email_queue_failure_does_not_block_push(self):
        self.email.side_effect = RuntimeError("broker unavailable")
        with self.assertLogs("django.test", level="ERROR"):
            with self.captureOnCommitCallbacks(execute=True):
                InviteService.create(
                    self.owner, self.org.pk, self.guest.email, "member"
                )
        self.assert_delivery(self.guest, "organization.invited")

    def test_acceptance_does_not_notify_former_inviter(self):
        OrganizationMember.objects.create(
            organization=self.org, user=self.guest, role="admin"
        )
        newcomer = User.objects.create_user(email="newcomer@example.com", password=None)
        with self.captureOnCommitCallbacks(execute=True):
            InviteService.create(self.guest, self.org.pk, newcomer.email, "member")
        token = parse_qs(urlparse(self.email.call_args.args[2]).query)["token"][0]
        OrganizationMember.objects.filter(
            organization=self.org, user=self.guest
        ).delete()
        with self.captureOnCommitCallbacks(execute=True):
            InviteService.accept(newcomer, token)
        self.assertFalse(
            Notification.objects.filter(
                data__event="organization.invite_accepted"
            ).exists()
        )

    def test_rollback_discards_all_domain_notifications_and_delivery(self):
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                TaskService.move(self.owner, self.task.pk, self.done, None)
                CommentService.create(self.owner, self.task.pk, "Rolled back")
                ChatService.send(
                    self.owner, self.channel.pk, "Hello", mention_ids=[self.member.pk]
                )
                InviteService.create(
                    self.owner, self.org.pk, self.guest.email, "member"
                )
                OrganizationService.add_member(
                    self.owner, self.org.pk, self.guest.email, "member"
                )
                transaction.set_rollback(True)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status_id, self.todo.pk)
        self.assertFalse(Notification.objects.exists())
        self.assertFalse(OrganizationInvite.objects.exists())
        self.assertFalse(Comment.objects.exists())
        self.assertFalse(ChatMessage.objects.exists())
        self.send.assert_not_called()
        self.email.assert_not_called()

    def test_notification_storage_failure_rolls_back_task_update_and_comment(self):
        with patch.object(
            NotificationService, "notify", side_effect=RuntimeError("database")
        ):
            with self.assertRaises(RuntimeError):
                TaskService.update(self.member, self.task.pk, {"assignee": self.owner})
            with self.assertRaises(RuntimeError):
                CommentService.create(self.owner, self.task.pk, "Not saved")
        self.task.refresh_from_db()
        self.assertEqual(self.task.assignee_id, self.member.pk)
        self.assertFalse(Comment.objects.exists())
