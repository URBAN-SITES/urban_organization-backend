from django.core.mail import EmailMessage
from django.db import transaction


def send_email_token(email: str, code: str, subject: str) -> None:
    """Queue token delivery after the transaction storing the token commits."""
    from core.tasks.email import send_email_task

    transaction.on_commit(lambda: send_email_task.delay(email, code, subject))


def send_email_token_sync(email: str, code: str, subject: str) -> None:
    """Send a token e-mail directly; used by the Celery worker."""
    message = EmailMessage(subject=subject, body=f"Your code is: {code}", to=[email])
    message.send()
