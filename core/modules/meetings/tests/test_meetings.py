import base64
import hashlib
import json
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from urllib.parse import urlparse

import jwt
import requests
from django.utils import timezone

from core.modules.kanban.tests.helpers import API, KanbanTestCase, client_for
from core.modules.meetings.models.meeting import MeetingConsent, MeetingRecording
from core.modules.meetings.services import storage
from core.modules.meetings.services.meetings import RecordingService

SECRET = "lk-secret-for-tests-0123456789abcdef"
ENV = {
    "LIVEKIT_URL": "wss://video.test",
    "LIVEKIT_API_KEY": "lk-key",
    "LIVEKIT_API_SECRET": SECRET,
    "RECORDINGS_S3_BUCKET": "recs",
    "RECORDINGS_S3_REGION": "auto",
    "RECORDINGS_S3_ENDPOINT": "https://s3.storage.test",
    "RECORDINGS_S3_ACCESS_KEY": "AK",
    "RECORDINGS_S3_SECRET_KEY": "SK",
}


def answer(status=200, body=None):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(body if body is not None else {}).encode()
    return result


class FakeHttp:
    """routes[(METHOD, path)] = Response; unknown routes answer 404."""

    def __init__(self):
        self.routes: dict = {}
        self.calls: list = []

    def __call__(self, method, url, **kwargs):
        parts = urlparse(url)
        self.calls.append((method, parts.netloc, parts.path, kwargs))
        return self.routes.get((method, parts.path), answer(404, {"msg": "nope"}))

    def sent(self, path) -> dict:
        return next(kw["json"] for _m, _h, p, kw in self.calls if p == path)


def soon(hours=1):
    return (timezone.now() + timedelta(hours=hours)).isoformat()


class MeetingTestCase(KanbanTestCase):
    def setUp(self):
        super().setUp()
        self.http = FakeHttp()
        stack = ExitStack()
        stack.enter_context(patch.dict("os.environ", ENV))
        stack.enter_context(
            patch(
                "requests.post",
                side_effect=lambda url, **kw: self.http("POST", url, **kw),
            )
        )
        stack.enter_context(
            patch(
                "requests.delete",
                side_effect=lambda url, **kw: self.http("DELETE", url, **kw),
            )
        )
        self.addCleanup(stack.close)
        self.sector = self.make_sector()
        self.share_sector(self.sector, self.member, "editor")
        self.viewer = self.add_org_member("viewer@a.com")
        self.share_sector(self.sector, self.viewer, "viewer")
        self.viewer_client = client_for(self.viewer)

    def schedule(self, client=None, **data):
        body = {
            "title": "Planning",
            "starts_at": soon(1),
            "ends_at": soon(2),
            **data,
        }
        res = (client or self.member_client).post(
            f"{API}sectors/{self.sector}/meetings/", body, format="json"
        )
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()

    def room_with_people(self):
        self.http.routes[("POST", "/twirp/livekit.RoomService/ListParticipants")] = (
            answer(
                body={
                    "participants": [
                        {"identity": str(self.member.id), "name": "Member"},
                        {"identity": "EG_x", "name": "", "kind": "EGRESS"},
                    ]
                }
            )
        )
        self.http.routes[("POST", "/twirp/livekit.Egress/StartRoomCompositeEgress")] = (
            answer(body={"egressId": "EG_1", "status": "EGRESS_STARTING"})
        )

    def webhook(self, event: dict, secret=SECRET):
        body = json.dumps(event).encode()
        claims = {
            "iss": "lk-key",
            "sha256": base64.b64encode(hashlib.sha256(body).digest()).decode(),
        }
        token = jwt.encode(claims, secret, algorithm="HS256")
        return self.client_class().post(
            f"{API}meetings/livekit/webhook/",
            body,
            content_type="application/webhook+json",
            HTTP_AUTHORIZATION=token,
        )


class ScheduleTests(MeetingTestCase):
    def test_editor_schedules_and_is_always_a_participant(self):
        meeting = self.schedule(participants=[str(self.viewer.id)])
        ids = {p["id"] for p in meeting["participants"]}
        self.assertEqual(ids, {str(self.member.id), str(self.viewer.id)})
        self.assertTrue(meeting["can_manage"])
        self.assertTrue(meeting["can_join"])

    def test_validation_and_roles(self):
        url = f"{API}sectors/{self.sector}/meetings/"
        body = {"title": "X", "starts_at": soon(2), "ends_at": soon(1)}
        self.assertEqual(
            self.member_client.post(url, body, format="json").status_code, 400
        )
        ok = {"title": "X", "starts_at": soon(1), "ends_at": soon(2)}
        self.assertEqual(
            self.viewer_client.post(url, ok, format="json").status_code, 403
        )
        outsider = self.add_org_member("out@a.com")
        stranger = {**ok, "participants": [str(outsider.id)]}
        self.assertEqual(
            self.member_client.post(url, stranger, format="json").status_code, 400
        )
        other_org = client_for(self.add_org_member("x@b.com"))
        self.assertEqual(other_org.get(url).status_code, 404)

    def test_upcoming_and_past_lists(self):
        self.schedule(title="Next")
        self.schedule(
            title="Old",
            starts_at=(timezone.now() - timedelta(days=2)).isoformat(),
            ends_at=(timezone.now() - timedelta(days=2, hours=-1)).isoformat(),
        )
        url = f"{API}sectors/{self.sector}/meetings/"
        upcoming = self.viewer_client.get(url, {"when": "upcoming"}).json()
        past = self.viewer_client.get(url, {"when": "past"}).json()
        self.assertEqual([m["title"] for m in upcoming], ["Next"])
        self.assertEqual([m["title"] for m in past], ["Old"])
        # the viewer was not invited
        self.assertFalse(upcoming[0]["can_join"])
        self.assertFalse(upcoming[0]["can_manage"])

    def test_only_organizer_or_manager_edits_and_cancels(self):
        meeting = self.schedule(participants=[str(self.viewer.id)])
        url = f"{API}meetings/{meeting['id']}/"
        self.assertEqual(
            self.viewer_client.patch(url, {"title": "Hack"}, format="json").status_code,
            403,
        )
        res = self.client.patch(url, {"title": "Renamed"}, format="json")  # org owner
        self.assertEqual(res.json()["title"], "Renamed")
        self.assertEqual(self.viewer_client.delete(url).status_code, 403)
        self.assertEqual(self.member_client.delete(url).status_code, 204)


class JoinTests(MeetingTestCase):
    def test_invited_person_gets_a_room_token_after_consent(self):
        meeting = self.schedule(participants=[str(self.viewer.id)])
        url = f"{API}meetings/{meeting['id']}/join/"
        self.assertEqual(
            self.viewer_client.post(url, {"consent": False}, format="json").status_code,
            400,
        )
        body = self.viewer_client.post(url, {"consent": True}, format="json").json()
        claims = jwt.decode(body["token"], SECRET, algorithms=["HS256"])
        self.assertEqual(claims["iss"], "lk-key")
        self.assertEqual(claims["sub"], str(self.viewer.id))
        self.assertEqual(claims["video"]["room"], f"meeting-{meeting['id']}")
        self.assertTrue(claims["video"]["roomJoin"])
        self.assertNotIn("roomRecord", claims["video"])
        self.assertEqual(body["url"], "wss://video.test")
        self.assertFalse(body["can_record"])
        self.assertTrue(
            MeetingConsent.objects.filter(
                meeting_id=meeting["id"], user=self.viewer
            ).exists()
        )

    def test_uninvited_and_outsiders_cannot_join(self):
        meeting = self.schedule()
        url = f"{API}meetings/{meeting['id']}/join/"
        res = self.viewer_client.post(url, {"consent": True}, format="json")
        self.assertEqual(res.status_code, 403)
        outsider = client_for(self.add_org_member("o@a.com"))
        self.assertEqual(
            outsider.post(url, {"consent": True}, format="json").status_code, 404
        )

    def test_missing_configuration_has_a_code(self):
        meeting = self.schedule()
        with patch.dict("os.environ", {"LIVEKIT_API_SECRET": ""}):
            res = self.member_client.post(
                f"{API}meetings/{meeting['id']}/join/", {"consent": True}, format="json"
            )
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json()["code"], "meetings_not_configured")


class RecordingTests(MeetingTestCase):
    def setUp(self):
        super().setUp()
        self.meeting = self.schedule(participants=[str(self.viewer.id)])
        self.base = f"{API}meetings/{self.meeting['id']}/recordings/"

    def start(self, client=None):
        self.room_with_people()
        res = (client or self.member_client).post(self.base)
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()

    def test_start_sends_the_bucket_and_tracks_participants(self):
        recording = self.start()
        sent = self.http.sent("/twirp/livekit.Egress/StartRoomCompositeEgress")
        self.assertEqual(sent["room_name"], f"meeting-{self.meeting['id']}")
        output = sent["file_outputs"][0]
        self.assertEqual(output["s3"]["bucket"], "recs")
        self.assertEqual(output["s3"]["endpoint"], "https://s3.storage.test")
        self.assertTrue(output["filepath"].endswith(".mp4"))
        self.assertEqual(recording["status"], "starting")
        self.assertEqual([p["name"] for p in recording["participants"]], ["Member"])
        # the server token carries only the record grant
        token = self.http.calls[-1][3]["headers"]["Authorization"].split()[1]
        self.assertEqual(
            jwt.decode(token, SECRET, algorithms=["HS256"])["video"],
            {"roomRecord": True},
        )
        self.assertEqual(self.member_client.post(self.base).status_code, 400)

    def test_rules_and_failures(self):
        self.assertEqual(self.viewer_client.post(self.base).status_code, 403)
        self.http.routes[("POST", "/twirp/livekit.RoomService/ListParticipants")] = (
            answer(body={"participants": []})
        )
        self.assertEqual(self.member_client.post(self.base).status_code, 400)
        self.http.routes[("POST", "/twirp/livekit.RoomService/ListParticipants")] = (
            answer(503, {"msg": "down"})
        )
        res = self.member_client.post(self.base)
        self.assertEqual(
            (res.status_code, res.json()["code"]), (502, "livekit_unavailable")
        )
        with patch.dict("os.environ", {"RECORDINGS_S3_BUCKET": ""}):
            res = self.member_client.post(self.base)
        self.assertEqual(res.json()["code"], "recordings_not_configured")
        self.assertFalse(MeetingRecording.objects.exists())

    def test_webhooks_move_the_recording_to_ready(self):
        self.start()
        room = {"name": f"meeting-{self.meeting['id']}"}
        self.assertEqual(
            self.webhook({"event": "egress_started"}, secret="wrong").status_code, 401
        )
        self.webhook(
            {
                "event": "egress_updated",
                "egressInfo": {"egressId": "EG_1", "status": "EGRESS_ACTIVE"},
            }
        )
        self.webhook(
            {
                "event": "participant_joined",
                "room": room,
                "participant": {"identity": str(self.viewer.id), "name": "Viewer"},
            }
        )
        res = self.webhook(
            {
                "event": "egress_ended",
                "egressInfo": {
                    "egressId": "EG_1",
                    "status": "EGRESS_COMPLETE",
                    "fileResults": [{"duration": "125000000000", "size": "2048"}],
                },
            }
        )
        self.assertEqual(res.status_code, 204)
        recording = MeetingRecording.objects.get()
        self.assertEqual(recording.status, "ready")
        self.assertEqual(
            (recording.duration_seconds, recording.size_bytes), (125, 2048)
        )
        self.assertEqual(
            [p["name"] for p in recording.participants], ["Member", "Viewer"]
        )

    def test_failed_egress_is_reported(self):
        self.start()
        self.webhook(
            {
                "event": "egress_ended",
                "egressInfo": {
                    "egressId": "EG_1",
                    "status": "EGRESS_FAILED",
                    "error": "upload failed",
                },
            }
        )
        recording = self.member_client.get(self.base).json()[0]
        self.assertEqual(
            (recording["status"], recording["error"]), ("failed", "upload failed")
        )
        self.assertIsNone(recording["play_url"])

    def test_stop(self):
        recording = self.start()
        self.http.routes[("POST", "/twirp/livekit.Egress/StopEgress")] = answer(body={})
        url = f"{self.base}{recording['id']}/stop/"
        self.assertEqual(self.viewer_client.post(url).status_code, 403)
        self.assertEqual(self.member_client.post(url).json()["status"], "processing")
        self.assertEqual(
            self.http.sent("/twirp/livekit.Egress/StopEgress"), {"egress_id": "EG_1"}
        )

    def test_signed_urls_and_download_only_for_managers(self):
        self.start()
        MeetingRecording.objects.update(status="ready")
        invited = self.viewer_client.get(self.base).json()[0]
        self.assertIn("X-Amz-Signature=", invited["play_url"])
        self.assertTrue(
            invited["play_url"].startswith("https://s3.storage.test/recs/meetings/")
        )
        self.assertIsNone(invited["download_url"])
        own = self.member_client.get(self.base).json()[0]
        self.assertIn("response-content-disposition=attachment", own["download_url"])
        download = f"{self.base}{own['id']}/download/"
        self.assertEqual(self.viewer_client.get(download).status_code, 403)
        self.assertIn(
            "X-Amz-Signature=", self.member_client.get(download).json()["url"]
        )
        stranger = client_for(self.add_org_member("s@a.com"))
        self.assertEqual(stranger.get(self.base).status_code, 404)

    def test_delete_and_retention_remove_the_file(self):
        self.start()
        MeetingRecording.objects.update(status="ready")
        self.http.routes[
            ("DELETE", "/recs/" + MeetingRecording.objects.get().file_key)
        ] = answer(204)
        recording_id = MeetingRecording.objects.get().id
        self.assertEqual(
            self.viewer_client.delete(f"{self.base}{recording_id}/").status_code, 403
        )
        self.assertEqual(
            self.member_client.delete(f"{self.base}{recording_id}/").status_code, 204
        )
        self.assertTrue(any(m == "DELETE" for m, *_ in self.http.calls))
        self.assertFalse(MeetingRecording.objects.exists())

        self.start()
        MeetingRecording.objects.update(
            status="ready", started_at=timezone.now() - timedelta(days=91)
        )
        self.assertEqual(RecordingService.purge_expired(), 1)
        self.assertFalse(MeetingRecording.objects.exists())


class PresignTests(MeetingTestCase):
    def test_matches_the_aws_sigv4_example(self):
        # https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-query-string-auth.html
        cfg = storage.BucketSettings(
            bucket="examplebucket",
            region="us-east-1",
            endpoint="https://s3.amazonaws.com",
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            path_style=False,
        )
        with patch.object(storage, "bucket_settings", return_value=cfg):
            url = storage.presign(
                "test.txt", expires=86400, now=datetime(2013, 5, 24, tzinfo=UTC)
            )
        self.assertTrue(
            url.startswith("https://examplebucket.s3.amazonaws.com/test.txt?")
        )
        self.assertTrue(
            url.endswith(
                "X-Amz-Signature=aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404"
            )
        )
