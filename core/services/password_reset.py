import secrets

from django.db import transaction
from rest_framework import exceptions, serializers

from core.models.password_reset import PasswordReset
from core.models.user import User
from core.response_messages import MSG_CODE_INVALID, MSG_SERVICE_UNAVAILABLE
from core.utils.email_token_sender import send_email_token


class PasswordResetService:
    @staticmethod
    def request_reset(email: str) -> None:
        user = User.objects.filter(email=email).first()
        if not user:
            return

        raw_code = f"{secrets.randbelow(1000000):06d}"

        try:
            with transaction.atomic():
                PasswordReset.objects.filter(user=user).delete()
                reset_code = PasswordReset(user=user)
                reset_code.set_code(raw_code)
                reset_code.save()
                send_email_token(user.email, raw_code, "Your password reset code")
        except Exception:
            raise exceptions.APIException(MSG_SERVICE_UNAVAILABLE)

    @staticmethod
    def verify_code(email: str, code: str) -> bool:
        user = User.objects.filter(email=email).first()
        reset_code = PasswordReset.objects.filter(user=user).first() if user else None

        if not reset_code or not reset_code.verify(code):
            raise serializers.ValidationError({"code": MSG_CODE_INVALID})

        return True

    @staticmethod
    def confirm_reset(email: str, code: str, new_password: str) -> None:
        PasswordResetService.verify_code(email, code)

        user = User.objects.get(email=email)
        user.set_password(new_password)
        user.save(update_fields=["password", "updated_at"])

        reset_code = PasswordReset.objects.get(user=user)
        reset_code.mark_used()
