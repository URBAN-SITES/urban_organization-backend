import secrets

from django.db import transaction
from rest_framework import exceptions, serializers, status

from core.models.email_verification import EmailVerification
from core.models.user import User
from core.response_messages import (
    MSG_CODE_INVALID,
    MSG_EMAIL_ALREADY_EXIST,
    MSG_SERVICE_UNAVAILABLE,
)
from core.utils.email_token_sender import send_email_token


class RegistrationService:
    @staticmethod
    def request_registration(email: str) -> None:
        user = User.objects.find_by_email(email)
        created = user is None
        if created:
            user, created = User.objects.get_or_create(
                email=email.strip().lower(), defaults={"is_active": False}
            )

        if not created and user.is_active:
            raise serializers.ValidationError({"email": MSG_EMAIL_ALREADY_EXIST})

        raw_code = f"{secrets.randbelow(1000000):06d}"
        try:
            with transaction.atomic():
                verification, __ = EmailVerification.objects.update_or_create(user=user)
                verification.set_code(raw_code)
                verification.save()
                send_email_token(user.email, raw_code, "Verify your e-mail")
        except Exception:
            raise exceptions.APIException(
                MSG_SERVICE_UNAVAILABLE,
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    @staticmethod
    def verify_code(email: str, code: str) -> bool:
        user = User.objects.find_by_email(email)
        verification = (
            EmailVerification.objects.filter(user=user).first() if user else None
        )

        if not verification or not verification.verify(code):
            raise serializers.ValidationError({"code": MSG_CODE_INVALID})
        return True

    @staticmethod
    def confirm_registration(email: str, code: str, name: str, password: str) -> None:
        RegistrationService.verify_code(email, code)

        user = User.objects.find_by_email(email)
        user.name = name
        user.set_password(password)
        user.is_active = True
        user.save(update_fields=["name", "password", "is_active", "updated_at"])

        verification = EmailVerification.objects.get(user=user)
        verification.mark_used()
