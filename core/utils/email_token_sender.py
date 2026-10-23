from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string


def send_email_token(email: str, code: str, subject: str) -> None:
    """Queue token delivery after the transaction storing the token commits."""
    from core.tasks.email import send_email_task

    transaction.on_commit(lambda: send_email_task.delay(email, code, subject))


def send_email_token_sync(email: str, code: str, subject: str) -> None:
    """Send a token e-mail directly; used by the Celery worker."""
    context = {"code": code, "subject": subject}
    message = EmailMultiAlternatives(
        subject=subject,
        body=render_to_string("emails/code.txt", context),
        to=[email],
    )
    message.attach_alternative(
        render_to_string("emails/code.html", context), "text/html"
    )
    message.send()
