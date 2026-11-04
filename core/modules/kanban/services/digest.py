"""E-mail digest: what is late, what is due soon and what was handed to you."""

from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from core.models.user import User
from core.modules.kanban.models.activity import TaskActivity
from core.modules.kanban.models.task import Task
from core.modules.kanban.services.sector import SectorService
from core.modules.user_settings.models.user_settings import UserSettings

LIMIT = 10


def _link(task: Task) -> str:
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/setores/{task.sector_id}?task={task.pk}"


def _rows(tasks) -> list[dict]:
    return [
        {
            "title": task.title,
            "project": task.sector.name,
            "due": task.due_date.strftime("%d/%m") if task.due_date else "",
            "link": _link(task),
        }
        for task in tasks[:LIMIT]
    ]


class DigestService:
    @staticmethod
    def content(user: User, weekly: bool, today=None) -> dict | None:
        """The digest of one person, or None when there is nothing to tell."""
        today = today or timezone.localdate()
        horizon = today + timedelta(days=7 if weekly else 1)
        since = timezone.now() - timedelta(days=7 if weekly else 1)
        mine = (
            Task.objects.filter(
                assignee=user,
                is_active=True,
                archived_at__isnull=True,
                completed_at__isnull=True,
                sector__is_active=True,
                sector__archived_at__isnull=True,
                sector__organization__is_active=True,
            )
            .select_related("sector")
            .order_by("due_date", "created_at")
        )
        # a person removed from a project keeps tasks there, but must not hear of them
        visible = {
            sector.pk
            for sector in {task.sector for task in mine}
            if SectorService.effective_role(user, sector)
        }
        mine = mine.filter(sector_id__in=visible)
        overdue = list(mine.filter(due_date__lt=today))
        soon = list(mine.filter(due_date__gte=today, due_date__lte=horizon))
        handed = list(
            mine.filter(
                pk__in=TaskActivity.objects.filter(
                    created_at__gte=since, changes__has_key="assignee"
                )
                .exclude(actor=user)
                .values("task_id")
            ).exclude(pk__in=[task.pk for task in overdue + soon])
        )
        if not (overdue or soon or handed):
            return None
        return {
            "name": (user.name or user.email).split(" ")[0],
            "weekly": weekly,
            "overdue": _rows(overdue),
            "overdue_count": len(overdue),
            "soon": _rows(soon),
            "soon_count": len(soon),
            "handed": _rows(handed),
            "settings_link": f"{settings.FRONTEND_URL.rstrip('/')}/configuracoes",
        }

    @staticmethod
    def send(user: User, weekly: bool) -> bool:
        context = DigestService.content(user, weekly)
        if context is None:
            return False
        subject = "Sua semana no Inceptum" if weekly else "Seu dia no Inceptum"
        message = EmailMultiAlternatives(
            subject=subject,
            body=render_to_string("emails/digest.txt", context),
            to=[user.email],
        )
        message.attach_alternative(
            render_to_string("emails/digest.html", context), "text/html"
        )
        message.send()
        return True

    @staticmethod
    def recipients(weekly: bool):
        flag = "email_weekly_digest" if weekly else "email_daily_digest"
        ids = UserSettings.objects.filter(**{flag: True}).values("user_id")
        return User.objects.filter(pk__in=ids, is_active=True).exclude(email="")
