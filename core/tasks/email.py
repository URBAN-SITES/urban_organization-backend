from celery import shared_task

from core.utils.email_token_sender import send_email_token_sync


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_email_task(email: str, code: str, subject: str) -> None:
    """Async e-mail: send_email_task.delay(email, code, subject)"""
    send_email_token_sync(email, code, subject)
