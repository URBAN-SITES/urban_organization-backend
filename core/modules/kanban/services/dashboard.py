from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from core.modules.kanban.models.task import Status, Task
from core.modules.kanban.services.activity import ActivityService
from core.modules.kanban.services.sector import SectorService
from core.modules.meetings.models.insight import MeetingInsight
from core.modules.meetings.models.meeting import Meeting
from core.modules.organizations.models.organization import OrganizationMember

WEEKS = 6
TODAY_LIMIT = 8
ACTIVITY_LIMIT = 8
FAVORITES_LIMIT = 6
MEETINGS_LIMIT = 5
INSIGHTS_LIMIT = 4
PARTICIPANTS_SHOWN = 4
EXCERPT_CHARS = 220


def _week_start(day):
    return day - timedelta(days=day.weekday())


def weekly_done(done, week_start):
    """Completed-task counts for the last WEEKS weeks, oldest first."""
    series = []
    for i in range(WEEKS - 1, -1, -1):
        start = week_start - timedelta(weeks=i)
        count = done.filter(
            completed_at__date__gte=start,
            completed_at__date__lt=start + timedelta(days=7),
        ).count()
        series.append({"week_start": start, "done": count})
    return series


def upcoming_meetings(sectors, now) -> list[dict]:
    """Meetings not over yet in the visible sectors, soonest first."""
    meetings = (
        Meeting.objects.filter(sector__in=sectors, ends_at__gte=now)
        .select_related("sector")
        .prefetch_related("participants")
        .order_by("starts_at")[:MEETINGS_LIMIT]
    )
    return [
        {
            "id": m.id,
            "title": m.title,
            "starts_at": m.starts_at,
            "ends_at": m.ends_at,
            "sector_id": m.sector_id,
            "sector_name": m.sector.name,
            "participant_count": len(m.participants.all()),
            "participants": [p.name for p in m.participants.all()][:PARTICIPANTS_SHOWN],
        }
        for m in meetings
    ]


def recent_insights(sectors) -> list[dict]:
    """Finished AI summaries of recordings in the visible sectors, newest first."""
    insights = (
        MeetingInsight.objects.filter(
            recording__meeting__sector__in=sectors,
            status=MeetingInsight.Status.DONE,
            summary__isnull=False,
        )
        .select_related("recording__meeting__sector")
        .order_by("-finished_at")[:INSIGHTS_LIMIT]
    )
    rows = []
    for insight in insights:
        recording = insight.recording
        meeting = recording.meeting
        summary = insight.summary or {}
        text = (summary.get("executive_summary") or "").strip()
        rows.append(
            {
                "meeting_id": meeting.id,
                "recording_id": recording.id,
                "meeting_title": meeting.title,
                "sector_name": meeting.sector.name,
                "finished_at": insight.finished_at,
                "duration_seconds": recording.duration_seconds,
                "excerpt": text[:EXCERPT_CHARS],
                "action_count": len(summary.get("actions") or []),
                "decision_count": len(summary.get("decisions") or []),
            }
        )
    return rows


class DashboardService:
    @staticmethod
    def summary(user, organization_id) -> dict:
        """Numbers for the home dashboard, limited to sectors the user can see."""
        sectors = SectorService.list_for(user, organization_id)
        tasks = Task.objects.filter(sector__in=sectors, is_active=True)
        open_tasks = tasks.exclude(status__category=Status.Category.DONE)
        mine = open_tasks.filter(assignee=user)

        today = timezone.localdate()
        week = _week_start(today)
        last_week = week - timedelta(days=7)
        week_end = week + timedelta(days=7)
        done = tasks.filter(completed_at__isnull=False)
        overdue = mine.overdue().order_by("due_date")

        def done_between(start, end):
            return done.filter(
                assignee=user, completed_at__date__gte=start, completed_at__date__lt=end
            ).count()

        first_overdue = overdue.first()
        due_soon = mine.filter(due_date__lte=today + timedelta(days=1)).order_by(
            "due_date"
        )
        favorites = SectorService.with_progress(
            sectors.filter(favorites__user=user)
        ).order_by("name")[:FAVORITES_LIMIT]
        return {
            "active_projects": sectors.count(),
            "members": OrganizationMember.objects.filter(
                organization_id=organization_id
            ).count(),
            "upcoming_meetings": upcoming_meetings(sectors, timezone.now()),
            "recent_insights": recent_insights(sectors),
            "in_progress": mine.filter(
                status__category=Status.Category.IN_PROGRESS
            ).count(),
            "favorites": [
                {
                    "id": s.id,
                    "name": s.name,
                    "color": s.color,
                    "task_total": s.task_total,
                    "task_done": s.task_done,
                }
                for s in favorites
            ],
            "recent_activity": [
                {
                    "id": a.id,
                    "action": a.action,
                    "changes": a.changes,
                    "actor_name": a.actor.name if a.actor_id else None,
                    "task_id": a.task_id,
                    "task_title": a.task.title,
                    "sector_id": a.task.sector_id,
                    "sector_name": a.task.sector.name,
                    "created_at": a.created_at,
                }
                for a in ActivityService.recent(sectors, ACTIVITY_LIMIT)
            ],
            "open_tasks": mine.count(),
            "due_this_week": mine.filter(
                due_date__gte=week, due_date__lt=week_end
            ).count(),
            "done_this_week": done_between(week, week_end),
            "done_last_week": done_between(last_week, week),
            "overdue": overdue.count(),
            "overdue_title": first_overdue.title if first_overdue else None,
            "today": [
                {
                    "id": t.id,
                    "title": t.title,
                    "sector_id": t.sector_id,
                    "sector_name": t.sector.name,
                    "due_date": t.due_date,
                    "is_overdue": t.due_date < today,
                }
                for t in due_soon.select_related("sector")[:TODAY_LIMIT]
            ],
            "weekly_done": weekly_done(done, week),
            "open_by_sector": [
                {"sector": row["sector__name"], "open": row["open"]}
                for row in open_tasks.values("sector__name")
                .annotate(open=Count("id"))
                .order_by("-open", "sector__name")
            ],
        }
