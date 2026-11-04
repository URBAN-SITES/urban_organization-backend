import logging

from celery import shared_task
from django.utils import timezone

from core.modules.kanban.models.sector import Sector
from core.modules.kanban.services.automation import AutomationService
from core.modules.kanban.services.digest import DigestService
from core.modules.kanban.services.task import TaskService

logger = logging.getLogger(__name__)


@shared_task
def send_digests() -> int:
    """Every morning: the daily digest, plus the weekly one on Mondays."""
    sent = 0
    kinds = [False] + ([True] if timezone.localdate().weekday() == 0 else [])
    for weekly in kinds:
        for user in DigestService.recipients(weekly):
            try:
                sent += DigestService.send(user, weekly)
            except Exception:  # one bad address must not stop the others
                logger.exception("digest failed for user %s", user.pk)
    return sent


@shared_task
def run_scheduled_rules() -> int:
    """Hourly: overdue automations and the auto-archive of every project."""
    for sector in Sector.objects.filter(
        is_active=True, auto_archive_days__isnull=False
    ):
        TaskService.auto_archive(sector)
    return AutomationService.run_overdue()
