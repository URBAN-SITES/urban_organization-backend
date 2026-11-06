import json
from unittest.mock import patch

from core.modules.kanban.models.task import Task
from core.modules.kanban.tests.helpers import API, client_for
from core.modules.meetings.models.insight import MeetingActionTask, MeetingInsight
from core.modules.meetings.models.meeting import Meeting, MeetingRecording
from core.modules.meetings.services import ai
from core.modules.meetings.services.insights import InsightPipeline
from core.modules.meetings.tasks import process_meeting_insight
from core.modules.meetings.tests.test_meetings import MeetingTestCase, answer

AI_ENV = {
    "MEETING_AI_ENGINE": "local",
    "MEETING_AI_ENABLED": "true",
    "OLLAMA_URL": "http://ollama.test",
}
SEGMENTS = [
    {"id": 0, "start": 0.0, "end": 4.0, "text": "Bom dia, vamos revisar a sprint."},
    {"id": 1, "start": 4.0, "end": 9.5, "text": "Decidimos adiar o deploy."},
    {"id": 2, "start": 9.5, "end": 15.0, "text": "Ana, revise o login até sexta."},
    {"id": 3, "start": 15.0, "end": 20.0, "text": "Alguém precisa atualizar a doc."},
]


def point(text, ids):
    return {"text": text, "segment_ids": ids}


def model_output(**changes):
    data = {
        "executive_summary": "A equipe revisou a sprint e adiou o deploy.",
        "topics": [{"title": "Revisão da sprint", "segment_ids": [0, 1]}],
        "decisions": [point("Adiar o deploy", [1])],
        "problems": [],
        "next_steps": [point("Revisar o login", [2])],
        "open_questions": [],
        "actions": [
            {
                "title": "Revisar o login",
                "description": "Revisão completa do fluxo de login.",
                "assignee": "Ana",
                "due_date": "2030-01-04",
                "segment_ids": [2],
            },
            {
                "title": "Atualizar a documentação",
                "description": "",
                "assignee": None,
                "due_date": "ontem",
                "segment_ids": [3],
            },
            {
                "title": "Ação inventada",
                "description": "",
                "assignee": None,
                "due_date": None,
                "segment_ids": [99],
            },
        ],
    }
    data.update(changes)
    return data


def ollama(body):
    return answer(body={"message": {"role": "assistant", "content": json.dumps(body)}})


class InsightTestCase(MeetingTestCase):
    def setUp(self):
        super().setUp()
        patcher = patch.dict("os.environ", AI_ENV)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.ana = self.add_org_member("ana@a.com")
        self.ana.name = "Ana Ribeiro"
        self.ana.save()
        self.share_sector(self.sector, self.ana, "editor")
        meeting = self.schedule(
            participants=[str(self.viewer.id)],
            starts_at="2030-01-01T10:00:00Z",
            ends_at="2030-01-01T11:00:00Z",
        )
        self.meeting_id = meeting["id"]
        self.recording = MeetingRecording.objects.create(
            meeting=Meeting.objects.get(id=self.meeting_id),
            egress_id="EG_ai",
            status=MeetingRecording.Status.READY,
            started_by=self.member,
            file_key="meetings/x/y/rec.mp4",
            duration_seconds=20,
            size_bytes=1000,
        )
        self.base = f"{API}meetings/{self.meeting_id}/recordings/{self.recording.id}/"
        self.transcribe = patch(
            "core.modules.meetings.services.ai.transcribe",
            return_value=(SEGMENTS, "pt", 20.0),
        ).start()
        self.extract = patch("core.modules.meetings.services.ai.extract_audio").start()
        self.addCleanup(patch.stopall)
        self.http.routes[("POST", "/api/chat")] = ollama(model_output())

    def run_pipeline(self) -> MeetingInsight:
        with self.captureOnCommitCallbacks(execute=True):
            InsightPipeline.enqueue(self.recording)
        return MeetingInsight.objects.get(recording=self.recording)


class PipelineTests(InsightTestCase):
    def test_recording_ready_webhook_starts_the_pipeline(self):
        self.recording.status = MeetingRecording.Status.PROCESSING
        self.recording.egress_id = "EG_hook"
        self.recording.save()
        with self.captureOnCommitCallbacks(execute=True):
            res = self.webhook(
                {
                    "event": "egress_ended",
                    "egressInfo": {
                        "egressId": "EG_hook",
                        "status": "EGRESS_COMPLETE",
                        "fileResults": [{"duration": "20000000000", "size": "1000"}],
                    },
                }
            )
        self.assertEqual(res.status_code, 204)
        insight = MeetingInsight.objects.get(recording=self.recording)
        self.assertEqual(insight.status, MeetingInsight.Status.DONE)

    def test_structured_summary_uses_real_quotes_and_never_guesses(self):
        insight = self.run_pipeline()
        self.assertEqual(insight.status, MeetingInsight.Status.DONE)
        self.assertEqual(len(insight.segments), 4)
        summary = insight.summary
        self.assertEqual(summary["decisions"][0]["source"]["start"], 4.0)
        self.assertEqual(summary["topics"][0]["source"]["end"], 9.5)
        actions = summary["actions"]
        # the action citing a segment that does not exist is dropped
        self.assertEqual(len(actions), 2)
        self.assertEqual(summary["dropped_actions"], 1)
        login, docs = actions
        self.assertEqual(login["assignee_id"], str(self.ana.id))
        self.assertEqual(login["due_date"], "2030-01-04")
        self.assertEqual(login["source"]["quote"], SEGMENTS[2]["text"])
        self.assertIsNone(docs["assignee_id"])
        self.assertIsNone(docs["due_date"])  # "ontem" is not a date

    def test_same_file_is_not_processed_twice(self):
        self.run_pipeline()
        InsightPipeline.run(MeetingInsight.objects.get().id)
        self.assertEqual(self.transcribe.call_count, 1)

    def test_summary_failure_keeps_transcript_and_retry_only_summarizes(self):
        self.http.routes[("POST", "/api/chat")] = ollama({"executive_summary": 1})
        insight = self.run_pipeline()
        self.assertEqual(insight.status, MeetingInsight.Status.FAILED)
        self.assertIn("schema", insight.error)
        self.assertEqual(len(insight.segments), 4)
        self.http.routes[("POST", "/api/chat")] = ollama(model_output())
        res = self.member_client.post(f"{self.base}insight/")
        self.assertEqual(res.status_code, 202, res.content)
        with self.captureOnCommitCallbacks(execute=True):
            pass
        process_meeting_insight.apply(args=[str(insight.id)])
        insight.refresh_from_db()
        self.assertEqual(insight.status, MeetingInsight.Status.DONE)
        self.assertEqual(self.transcribe.call_count, 1)

    def test_limits_fail_without_touching_the_recording(self):
        self.recording.duration_seconds = 10 * 60 * 60
        self.recording.save()
        insight = self.run_pipeline()
        self.assertEqual(insight.status, MeetingInsight.Status.FAILED)
        self.assertIn("limit", insight.error)
        self.transcribe.assert_not_called()
        self.assertTrue(MeetingRecording.objects.filter(id=self.recording.id).exists())
        self.assertFalse(any(m == "DELETE" for m, *_ in self.http.calls))

    def test_engine_down_is_retried_then_marked_failed(self):
        self.http.routes[("POST", "/api/chat")] = answer(503, {})
        insight = MeetingInsight.objects.create(
            recording=self.recording, transcribe_model="m"
        )
        with self.assertRaises(ai.TransientError):
            InsightPipeline.run(insight.id)
        insight.refresh_from_db()
        self.assertEqual(insight.status, MeetingInsight.Status.PENDING)
        with patch.object(process_meeting_insight, "max_retries", 0):
            process_meeting_insight.apply(args=[str(insight.id)], retries=3)
        insight.refresh_from_db()
        self.assertEqual(insight.status, MeetingInsight.Status.FAILED)
        self.assertEqual(len(insight.segments), 4)

    def test_disabled_never_runs(self):
        off = {"MEETING_AI_ENGINE": "", "MEETING_AI_ENABLED": "", "GEMINI_API_KEY": ""}
        with patch.dict("os.environ", off):
            InsightPipeline.on_recording_ready(self.recording)
            res = self.member_client.get(f"{self.base}insight/")
        self.assertFalse(MeetingInsight.objects.exists())
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json()["code"], "insights_not_configured")


class FakeGemini:
    """Stands in for google.genai.Client: one upload, two JSON answers."""

    def __init__(self, transcript, summary):
        self.answers = [transcript, summary]
        self.deleted = []
        self.files = self
        self.models = self

    def upload(self, file, config):
        return type("File", (), {"name": "files/1", "state": None})()

    def delete(self, name):
        self.deleted.append(name)

    def generate_content(self, model, contents, config):
        return type("Answer", (), {"text": json.dumps(self.answers.pop(0))})()


class GeminiEngineTests(InsightTestCase):
    def test_gemini_is_used_when_its_key_is_set(self):
        transcript = {
            "language": "pt",
            "segments": [
                {"start": s["start"], "end": s["end"], "text": s["text"]}
                for s in SEGMENTS
            ],
        }
        fake = FakeGemini(transcript, model_output())
        env = {"MEETING_AI_ENGINE": "", "MEETING_AI_ENABLED": "", "GEMINI_API_KEY": "k"}
        with (
            patch.dict("os.environ", env),
            patch.object(ai, "_gemini", return_value=fake),
            patch.object(ai, "_download", return_value="video/mp4"),
        ):
            self.assertEqual(ai.engine(), "gemini")
            insight = self.run_pipeline()
        self.assertEqual(insight.status, MeetingInsight.Status.DONE, insight.error)
        self.assertEqual(
            [s["text"] for s in insight.segments], [s["text"] for s in SEGMENTS]
        )
        self.assertEqual(insight.audio_seconds, 20.0)
        self.assertTrue(insight.summary["executive_summary"])
        self.assertEqual(insight.summary_model, ai.GEMINI_MODEL)
        self.assertEqual(fake.deleted, ["files/1"])  # the upload is not kept
        self.transcribe.assert_not_called()


class InsightApiTests(InsightTestCase):
    def test_participants_read_outsiders_do_not(self):
        self.run_pipeline()
        res = self.viewer_client.get(f"{self.base}insight/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "done")
        outsider = client_for(self.add_org_member("out@a.com"))
        self.assertIn(outsider.get(f"{self.base}insight/").status_code, (403, 404))

    def test_only_managers_start_and_never_while_done(self):
        self.assertEqual(
            self.viewer_client.post(f"{self.base}insight/").status_code, 403
        )
        self.run_pipeline()
        self.assertEqual(
            self.member_client.post(f"{self.base}insight/").status_code, 400
        )

    def test_markdown_export(self):
        self.run_pipeline()
        res = self.viewer_client.get(f"{self.base}insight/export/")
        self.assertEqual(res.status_code, 200)
        text = res.content.decode()
        self.assertIn("## Decisões", text)
        self.assertIn("sem responsável identificado", text)
        self.assertIn("[00:09] Ana, revise o login até sexta.", text)

    def test_actions_become_tasks_once_after_review(self):
        self.run_pipeline()
        url = f"{self.base}insight/tasks/"
        items = [
            {"index": 0, "title": "Revisar login", "assignee": str(self.ana.id)},
            {"index": 1, "title": "Doc", "assignee": None, "due_date": None},
        ]
        self.assertEqual(
            self.viewer_client.post(url, {"items": items}, format="json").status_code,
            403,
        )
        res = self.member_client.post(url, {"items": items}, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(len(res.json()["created"]), 2)
        again = self.member_client.post(url, {"items": items}, format="json")
        self.assertEqual(again.json(), {"created": [], "skipped": [0, 1]})
        self.assertEqual(Task.objects.filter(sector_id=self.sector).count(), 2)
        task = Task.objects.get(title="Revisar login")
        self.assertEqual(task.assignee, self.ana)
        self.assertIn("Ana, revise o login", task.description)
        self.assertEqual(MeetingActionTask.objects.count(), 2)
        data = self.member_client.get(f"{self.base}insight/").json()
        self.assertTrue(all(a["created"] for a in data["summary"]["actions"]))

    def test_unknown_action_is_rejected(self):
        self.run_pipeline()
        res = self.member_client.post(
            f"{self.base}insight/tasks/",
            {"items": [{"index": 7, "title": "x"}]},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
