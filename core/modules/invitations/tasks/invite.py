from celery import shared_task
from django.core.mail import EmailMessage


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_invite_email_task(email: str, organization: str, link: str) -> None:
    """Async invitation e-mail: send_invite_email_task.delay(email, org_name, link)"""
    EmailMessage(
        subject=f"You were invited to {organization}",
        body=f"You were invited to join {organization}.\nAccept here: {link}",
        to=[email],
    ).send()
