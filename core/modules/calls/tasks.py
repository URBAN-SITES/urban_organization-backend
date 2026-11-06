from celery import shared_task

from core.modules.calls.services.calls import CallService


@shared_task
def expire_calls() -> int:
    """Unanswered calls become missed; abandoned ones are closed."""
    return CallService.expire_unanswered()
