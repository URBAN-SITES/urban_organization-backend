from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_invite_email_task(email: str, organization: str, link: str) -> None:
    """Async invitation e-mail: send_invite_email_task.delay(email, org_name, link)"""
    context = {"organization": organization, "link": link}
    message = EmailMultiAlternatives(
        subject=f"You were invited to {organization}",
        body=render_to_string("emails/invitation.txt", context),
        to=[email],
    )
    message.attach_alternative(
        render_to_string("emails/invitation.html", context), "text/html"
    )
    message.send()
