from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models.user import User
from core.modules.chat.models.chat import ChatChannel, ChatMessage
from core.modules.organizations.models.organization import OrganizationMember
from core.modules.organizations.services.organization import OrganizationService
from core.modules.teams.services.team import TeamService

API = "/api/v1/"
PUSH = "core.modules.chat.services.chat.send_to_user"


def make_user(email, name="User"):
    return User.objects.create_user(email=email, password="x12345678!", name=name)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


class ChatTestCase(TestCase):
    def setUp(self):
        self.owner = make_user("owner@a.com", "Owner")
        self.org = OrganizationService.create(self.owner, name="Acme")
        self.ana = self.join("ana@a.com", "Ana")
        self.bob = self.join("bob@a.com", "Bob")
        self.clients = {u: client_for(u) for u in (self.owner, self.ana, self.bob)}
        self.channels_url = f"{API}organizations/{self.org.id}/chat/channels/"

    def join(self, email, name, role="member"):
        user = make_user(email, name)
        OrganizationMember.objects.create(organization=self.org, user=user, role=role)
        return user

    def channels(self, user):
        res = self.clients[user].get(self.channels_url)
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()

    def general(self, user):
        return next(c for c in self.channels(user) if c["kind"] == "organization")

    def say(self, user, channel_id, content="hi", **extra):
        return self.clients[user].post(
            f"{API}chat/channels/{channel_id}/messages/",
            {"content": content, **extra},
            format="json",
        )

    def make_team(self, *members, name="Ops"):
        team = TeamService.create(self.owner, self.org.id, name=name)
        for user in members:
            TeamService.add_member(self.owner, self.org.id, team.id, user.id, "member")
        return team

    def team_channel(self, user):
        return next(c for c in self.channels(user) if c["kind"] == "team")


class ChannelTests(ChatTestCase):
    def test_everyone_gets_one_general_channel(self):
        ids = {self.general(u)["id"] for u in self.clients}
        self.assertEqual(len(ids), 1)
        self.assertEqual(self.general(self.ana)["name"], "General")
        self.assertEqual(
            ChatChannel.objects.filter(
                organization=self.org, kind="organization"
            ).count(),
            1,
        )

    def test_team_channel_is_visible_only_to_team_members(self):
        team = self.make_team(self.ana)
        channel = self.team_channel(self.ana)
        self.assertEqual((channel["name"], channel["team_id"]), ("Ops", str(team.id)))
        self.assertEqual([c["kind"] for c in self.channels(self.bob)], ["organization"])
        self.assertEqual(self.say(self.bob, channel["id"]).status_code, 404)
        self.assertEqual(self.say(self.ana, channel["id"]).status_code, 201)
        # leaving the team revokes access
        member = team.members.get(user=self.ana)
        TeamService.remove_member(self.owner, self.org.id, team.id, member.id)
        self.assertEqual(self.say(self.ana, channel["id"]).status_code, 404)

    def test_outsiders_and_other_organizations_have_no_access(self):
        general = self.general(self.ana)["id"]
        stranger = make_user("s@a.com")
        self.clients[stranger] = client_for(stranger)
        self.assertEqual(self.clients[stranger].get(self.channels_url).status_code, 404)
        res = self.clients[stranger].get(f"{API}chat/channels/{general}/messages/")
        self.assertEqual(res.status_code, 404)

    def test_direct_conversation(self):
        url = f"{API}organizations/{self.org.id}/chat/direct/"
        first = self.clients[self.ana].post(url, {"user_id": str(self.bob.id)})
        again = self.clients[self.bob].post(url, {"user_id": str(self.ana.id)})
        self.assertEqual(first.json()["id"], again.json()["id"])
        self.assertEqual((first.json()["name"], again.json()["name"]), ("Bob", "Ana"))
        self.assertEqual(ChatChannel.objects.filter(kind="direct").count(), 1)
        self.assertEqual(
            self.clients[self.ana].post(url, {"user_id": str(self.ana.id)}).status_code,
            400,
        )
        stranger = make_user("s@a.com")
        res = self.clients[self.ana].post(url, {"user_id": str(stranger.id)})
        self.assertEqual(res.status_code, 400)
        # a third member cannot read it
        direct = first.json()["id"]
        res = self.clients[self.owner].get(f"{API}chat/channels/{direct}/messages/")
        self.assertEqual(res.status_code, 404)
        self.assertIn("direct", [c["kind"] for c in self.channels(self.ana)])
        self.assertNotIn("direct", [c["kind"] for c in self.channels(self.owner)])


class MessageTests(ChatTestCase):
    def test_send_list_newest_first_and_validation(self):
        general = self.general(self.ana)["id"]
        for text in ("one", "two", "three"):
            self.assertEqual(self.say(self.ana, general, text).status_code, 201)
        url = f"{API}chat/channels/{general}/messages/"
        results = self.clients[self.bob].get(url).json()["results"]
        self.assertEqual([m["content"] for m in results], ["three", "two", "one"])
        self.assertEqual(results[0]["author_name"], "Ana")
        self.assertEqual(self.say(self.ana, general, "").status_code, 400)
        self.assertEqual(self.say(self.ana, general, "x" * 4001).status_code, 400)

    def test_after_filter(self):
        general = self.general(self.ana)["id"]
        self.say(self.ana, general, "old")
        ChatMessage.objects.update(created_at=timezone.now() - timedelta(hours=1))
        self.say(self.ana, general, "new")
        cutoff = (timezone.now() - timedelta(minutes=5)).isoformat()
        url = f"{API}chat/channels/{general}/messages/"
        res = self.clients[self.bob].get(url, {"after": cutoff})
        self.assertEqual([m["content"] for m in res.json()["results"]], ["new"])
        self.assertEqual(
            self.clients[self.bob].get(url, {"after": "yesterday"}).status_code, 400
        )

    def test_reply_must_be_in_the_same_channel(self):
        general = self.general(self.ana)["id"]
        parent = self.say(self.ana, general, "question").json()
        reply = self.say(self.bob, general, "answer", reply_to=parent["id"])
        self.assertEqual(reply.json()["reply_to_id"], parent["id"])
        self.make_team(self.ana)
        team = self.team_channel(self.ana)["id"]
        res = self.say(self.ana, team, "x", reply_to=parent["id"])
        self.assertEqual(res.status_code, 400)

    def test_unread_counts(self):
        general = self.general(self.ana)["id"]
        self.say(self.ana, general, "a")
        self.say(self.ana, general, "b")
        self.assertEqual(self.general(self.bob)["unread_count"], 2)
        self.assertEqual(self.general(self.ana)["unread_count"], 0)  # own messages
        res = self.clients[self.bob].post(f"{API}chat/channels/{general}/read/")
        self.assertEqual(res.status_code, 204)
        self.assertEqual(self.general(self.bob)["unread_count"], 0)
        self.say(self.ana, general, "c")
        self.assertEqual(self.general(self.bob)["unread_count"], 1)
        # replying marks the channel as read for the sender
        self.say(self.bob, general, "ok")
        self.assertEqual(self.general(self.bob)["unread_count"], 0)

    def test_edit_rules(self):
        general = self.general(self.ana)["id"]
        message = self.say(self.ana, general, "typo").json()
        url = f"{API}chat/messages/{message['id']}/"
        self.assertEqual(
            self.clients[self.bob].patch(url, {"content": "x"}).status_code, 403
        )
        res = self.clients[self.ana].patch(url, {"content": "fixed"})
        self.assertEqual(res.json()["content"], "fixed")
        self.assertIsNotNone(res.json()["edited_at"])
        self.clients[self.ana].delete(url)
        self.assertEqual(
            self.clients[self.ana].patch(url, {"content": "x"}).status_code, 400
        )

    def test_delete_rules_and_soft_delete(self):
        general = self.general(self.ana)["id"]
        message = self.say(self.ana, general, "secret").json()
        url = f"{API}chat/messages/{message['id']}/"
        self.assertEqual(self.clients[self.bob].delete(url).status_code, 403)
        self.assertEqual(
            self.clients[self.owner].delete(url).status_code, 204
        )  # org owner moderates
        stored = ChatMessage.objects.get(id=message["id"])
        self.assertEqual((stored.content, stored.deleted_at is not None), ("", True))
        listed = self.clients[self.bob].get(f"{API}chat/channels/{general}/messages/")
        self.assertIsNotNone(listed.json()["results"][0]["deleted_at"])
        self.assertEqual(
            self.clients[self.owner].delete(url).status_code, 204
        )  # idempotent

    def test_org_admin_cannot_moderate_direct_conversations(self):
        direct = (
            self.clients[self.ana]
            .post(
                f"{API}organizations/{self.org.id}/chat/direct/",
                {"user_id": str(self.bob.id)},
            )
            .json()["id"]
        )
        message = self.say(self.ana, direct, "private").json()
        res = self.clients[self.owner].delete(f"{API}chat/messages/{message['id']}/")
        self.assertEqual(res.status_code, 404)  # the owner cannot even see it
        res = self.clients[self.bob].delete(f"{API}chat/messages/{message['id']}/")
        self.assertEqual(res.status_code, 403)


class BroadcastTests(ChatTestCase):
    def pushed(self, user, channel_id, content="hello"):
        with patch(PUSH) as push, self.captureOnCommitCallbacks(execute=True):
            self.say(user, channel_id, content)
        return push

    def test_general_message_reaches_every_member(self):
        push = self.pushed(self.ana, self.general(self.ana)["id"])
        users = {call.args[0] for call in push.call_args_list}
        self.assertEqual(users, {self.owner.id, self.ana.id, self.bob.id})
        payload = push.call_args.args[1]
        self.assertEqual(payload["type"], "chat.message")
        self.assertEqual(payload["message"]["content"], "hello")

    def test_team_message_reaches_only_the_team(self):
        outsider = self.join("dan@a.com", "Dan")  # in the organization, not in the team
        self.make_team(self.ana, self.bob)  # the creator (owner) becomes team lead
        channel = self.team_channel(self.ana)["id"]
        push = self.pushed(self.ana, channel)
        users = {call.args[0] for call in push.call_args_list}
        self.assertEqual(users, {self.owner.id, self.ana.id, self.bob.id})
        self.assertNotIn(outsider.id, users)

    def test_edit_and_delete_are_broadcast_and_push_failure_is_ignored(self):
        general = self.general(self.ana)["id"]
        message = self.say(self.ana, general, "v1").json()
        url = f"{API}chat/messages/{message['id']}/"
        with patch(PUSH) as push, self.captureOnCommitCallbacks(execute=True):
            self.clients[self.ana].patch(url, {"content": "v2"})
            self.clients[self.ana].delete(url)
        events = {call.args[1]["type"] for call in push.call_args_list}
        self.assertEqual(events, {"chat.message_updated", "chat.message_deleted"})
        with (
            patch(PUSH, side_effect=RuntimeError("down")),
            self.captureOnCommitCallbacks(execute=True),
        ):
            res = self.say(self.ana, general, "still saved")
        self.assertEqual(res.status_code, 201)
        self.assertTrue(ChatMessage.objects.filter(content="still saved").exists())


class TeamsChannelTests(ChatTestCase):
    def setUp(self):
        super().setUp()
        self.carol = self.join("carol@a.com", "Carol")
        self.clients[self.carol] = client_for(self.carol)
        self.team_a = self.make_team(self.ana, name="Design")
        self.team_b = self.make_team(self.bob, name="Dev")
        self.url = f"{API}organizations/{self.org.id}/chat/team-channels/"

    def create(self, user, *teams, **extra):
        return self.clients[user].post(
            self.url, {"team_ids": [str(t.id) for t in teams], **extra}, format="json"
        )

    def test_members_of_both_teams_talk_and_others_cannot(self):
        res = self.create(self.ana, self.team_a, self.team_b)
        self.assertEqual(res.status_code, 201, res.content)
        channel = res.json()
        self.assertEqual(channel["kind"], "teams")
        self.assertEqual(channel["name"], "Design & Dev")
        self.assertCountEqual(
            channel["team_ids"], [str(self.team_a.id), str(self.team_b.id)]
        )
        self.assertEqual(self.say(self.ana, channel["id"], "hi both").status_code, 201)
        bob_view = [c["id"] for c in self.channels(self.bob) if c["kind"] == "teams"]
        self.assertEqual(bob_view, [channel["id"]])
        self.assertEqual(self.say(self.bob, channel["id"], "hello").status_code, 201)
        self.assertEqual(self.say(self.carol, channel["id"]).status_code, 404)
        self.assertEqual(
            [c for c in self.channels(self.carol) if c["kind"] == "teams"], []
        )

    def test_creator_must_belong_to_a_team_or_be_org_admin(self):
        self.assertEqual(
            self.create(self.carol, self.team_a, self.team_b).status_code, 403
        )
        self.assertEqual(
            self.create(self.owner, self.team_a, self.team_b).status_code, 201
        )

    def test_validation(self):
        self.assertEqual(
            self.create(self.ana, self.team_a).status_code, 400
        )  # one team
        same = self.clients[self.ana].post(
            self.url, {"team_ids": [str(self.team_a.id)] * 2}, format="json"
        )
        self.assertEqual(same.status_code, 400)
        stranger = make_user("s@a.com")
        other_org = OrganizationService.create(stranger, name="Other")
        alien = TeamService.create(stranger, other_org.id, name="Alien")
        self.assertEqual(self.create(self.ana, self.team_a, alien).status_code, 400)
        named = self.create(self.ana, self.team_a, self.team_b, name="Launch")
        self.assertEqual(named.json()["name"], "Launch")

    def test_leaving_the_only_linked_team_revokes_access(self):
        channel = self.create(self.ana, self.team_a, self.team_b).json()["id"]
        member = self.team_b.members.get(user=self.bob)
        TeamService.remove_member(self.owner, self.org.id, self.team_b.id, member.id)
        self.assertEqual(self.say(self.bob, channel).status_code, 404)
        self.assertEqual(self.say(self.ana, channel).status_code, 201)

    def test_broadcast_reaches_each_member_once(self):
        channel = self.create(self.ana, self.team_a, self.team_b).json()["id"]
        with patch(PUSH) as push, self.captureOnCommitCallbacks(execute=True):
            self.say(self.ana, channel, "hello")
        users = [call.args[0] for call in push.call_args_list]
        # the owner leads both teams but must not be notified twice
        self.assertCountEqual(users, [self.owner.id, self.ana.id, self.bob.id])
