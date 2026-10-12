from django.core.mail import EmailMessage


def send_email_token(email: str, code: str, subject: str) -> None:
    message = EmailMessage(subject=subject, body=f"Your code is: {code}", to=[email])
    try:
        message.send()
    except Exception as e:
        raise e
