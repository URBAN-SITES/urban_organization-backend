from celery import shared_task

from core.modules.meetings.models.insight import MeetingInsight
from core.modules.meetings.services.ai import TransientError
from core.modules.meetings.services.insights import InsightPipeline

MAX_RETRIES = 3


@shared_task(
    bind=True,
    acks_late=True,
    max_retries=MAX_RETRIES,
    # transcription on CPU can take about as long as the meeting itself
    soft_time_limit=2 * 60 * 60,
    time_limit=2 * 60 * 60 + 120,
)
def process_meeting_insight(self, insight_id: str) -> None:
    """Transcribe and summarize one recording; retries only transient failures."""
    try:
        InsightPipeline.run(insight_id)
    except TransientError as exc:
        if self.request.retries >= MAX_RETRIES:
            InsightPipeline.mark(insight_id, MeetingInsight.Status.FAILED, str(exc))
            return
        raise self.retry(exc=exc, countdown=120 * 2**self.request.retries)
