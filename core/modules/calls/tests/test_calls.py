from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

from core.modules.calls.models.call import Call, CallParticipant
from core.modules.calls.services.calls import CallService
from core.modules.chat.models.chat import ChatMessage
from core.modules.chat.tests.test_chat import API, ChatTestCase
from core.modules.notifications.models.notification import Notification

CALL_PUSH = "core.modules.calls.services.calls.send_to_user"
CHAT_PUSH = "core.modules.chat.services.chat.send_to_user"


@patch(CHAT_PUSH)
@patch(CALL_PUSH)
class CallTests(ChatTestCase):
    def direct(self, user, other):
        res = self.clients[user].post(
            f"{API}organizations/{self.org.id}/chat/direct/",
            {"user_id": str(other.id)},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()["id"]

    def start(self, user, channel_id, kind="video"):
        return self.clients[user].post(
            f"{API}calls/", {"channel_id": channel_id, "kind": kind}, format="json"
        )

    def act(self, user, call_id, action, body=None):
        return self.clients[user].post(
            f"{API}calls/{call_id}/{action}/", body or {}, format="json"
        )

    def test_direct_call_rings_answers_and_ends_with_a_summary(self, call_push, _chat):
        channel = self.direct(self.ana, self.bob)
        with self.captureOnCommitCallbacks(execute=True):
            res = self.start(self.ana, channel)
        self.assertEqual(res.status_code, 201, res.content)
        call = res.json()
        self.assertEqual(call["status"], "ringing")
        ringing = [c for c in call_push.call_args_list if c.args[0] == self.bob.id]
        self.assertEqual(ringing[0].args[1]["type"], "call.ringing")
        self.assertTrue(
            Notification.objects.filter(
                user=self.bob, data__event="call.incoming"
            ).exists()
        )

        joined = self.act(self.bob, call["id"], "join")
        self.assertEqual(joined.json()["status"], "ongoing")

        ended = self.act(self.bob, call["id"], "leave")
        self.assertEqual(
            ended.json()["status"], "ended"
        )  # direct: one side leaving ends
        summary = ChatMessage.objects.get(call_id=call["id"])
        self.assertEqual(str(summary.channel_id), channel)
        listed = self.clients[self.bob].get(f"{API}chat/channels/{channel}/messages/")
        self.assertEqual(listed.json()["results"][0]["call"]["status"], "ended")

    def test_caller_hanging_up_before_an_answer_is_a_missed_call(self, *_):
        channel = self.direct(self.ana, self.bob)
        call = self.start(self.ana, channel, "audio").json()
        self.assertEqual(
            self.act(self.ana, call["id"], "leave").json()["status"], "missed"
        )
        self.assertTrue(
            Notification.objects.filter(
                user=self.bob, data__event="call.missed"
            ).exists()
        )

    def test_everyone_declining_ends_the_call(self, *_):
        channel = self.direct(self.ana, self.bob)
        call = self.start(self.ana, channel).json()
        res = self.act(self.bob, call["id"], "decline")
        self.assertEqual(res.json()["status"], "declined")

    def test_group_call_lasts_until_the_last_person_leaves(self, *_):
        channel = self.general(self.ana)["id"]
        call = self.start(self.ana, channel).json()
        self.assertEqual(len(call["participants"]), 3)  # owner, ana and bob
        self.act(self.bob, call["id"], "join")
        self.act(self.owner, call["id"], "join")
        self.assertEqual(
            self.act(self.ana, call["id"], "leave").json()["status"], "ongoing"
        )
        self.act(self.bob, call["id"], "leave")
        self.assertEqual(
            self.act(self.owner, call["id"], "leave").json()["status"], "ended"
        )

    def test_only_one_live_call_per_channel(self, *_):
        channel = self.direct(self.ana, self.bob)
        first = self.start(self.ana, channel).json()
        res = self.start(self.bob, channel)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["call_id"], first["id"])

    @override_settings(CALL_MAX_PARTICIPANTS=2)
    def test_channels_bigger_than_the_limit_are_refused(self, *_):
        res = self.start(self.ana, self.general(self.ana)["id"])
        self.assertEqual(res.status_code, 400)

    def test_people_outside_the_channel_cannot_start_or_see_it(self, *_):
        channel = self.direct(self.ana, self.bob)
        self.assertEqual(self.start(self.owner, channel).status_code, 404)
        call = self.start(self.ana, channel).json()
        res = self.clients[self.owner].get(f"{API}calls/{call['id']}/")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(self.act(self.owner, call["id"], "join").status_code, 404)

    def test_signals_go_only_to_joined_participants(self, call_push, _chat):
        channel = self.direct(self.ana, self.bob)
        call = self.start(self.ana, channel).json()
        signal = {"to_user_id": str(self.bob.id), "data": {"sdp": {"type": "offer"}}}
        # bob has not answered yet: nothing to relay to
        self.assertEqual(
            self.act(self.ana, call["id"], "signal", signal).status_code, 404
        )
        self.act(self.bob, call["id"], "join")
        call_push.reset_mock()
        res = self.act(self.ana, call["id"], "signal", signal)
        self.assertEqual(res.status_code, 204)
        call_push.assert_called_once()
        user_id, payload = call_push.call_args.args
        self.assertEqual(user_id, self.bob.id)
        self.assertEqual(payload["from_user_id"], str(self.ana.id))
        huge = {"to_user_id": str(self.bob.id), "data": {"sdp": "x" * 70_000}}
        self.assertEqual(
            self.act(self.ana, call["id"], "signal", huge).status_code, 400
        )

    def test_media_flags_are_shared(self, *_):
        channel = self.direct(self.ana, self.bob)
        call = self.start(self.ana, channel).json()
        res = self.act(self.ana, call["id"], "media", {"muted": True})
        me = next(
            p for p in res.json()["participants"] if p["user_id"] == str(self.ana.id)
        )
        self.assertTrue(me["muted"])

    def test_unanswered_calls_expire_as_missed(self, *_):
        channel = self.direct(self.ana, self.bob)
        call = self.start(self.ana, channel).json()
        Call.objects.filter(id=call["id"]).update(
            created_at=timezone.now() - timedelta(minutes=5)
        )
        self.assertEqual(CallService.expire_unanswered(), 1)
        self.assertEqual(Call.objects.get(id=call["id"]).status, "missed")
        # a new call is possible again
        self.assertEqual(self.start(self.bob, channel).status_code, 201)

    def test_closing_the_last_socket_leaves_the_call(self, *_):
        channel = self.direct(self.ana, self.bob)
        call = self.start(self.ana, channel).json()
        self.act(self.bob, call["id"], "join")
        self.assertEqual(CallService.leave_all(self.bob), 1)
        self.assertEqual(Call.objects.get(id=call["id"]).status, "ended")
        self.assertEqual(
            CallParticipant.objects.get(call_id=call["id"], user=self.bob).state, "left"
        )

    @override_settings(TURN_URLS=["turn:turn.example.com"], TURN_SECRET="s3cret")
    def test_ice_servers_include_short_lived_turn_credentials(self, *_):
        servers = self.clients[self.ana].get(f"{API}calls/ice-servers/").json()
        turn = servers["ice_servers"][-1]
        self.assertEqual(turn["urls"], ["turn:turn.example.com"])
        self.assertTrue(turn["username"].endswith(str(self.ana.id)))
        self.assertTrue(turn["credential"])

    def test_history_lists_my_calls(self, *_):
        channel = self.direct(self.ana, self.bob)
        self.start(self.ana, channel)
        self.assertEqual(len(self.clients[self.bob].get(f"{API}calls/").json()), 1)
        self.assertEqual(self.clients[self.owner].get(f"{API}calls/").json(), [])
