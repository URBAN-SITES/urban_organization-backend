import secrets

from django.db import transaction
from rest_framework import exceptions, serializers

from core.models.email_change import EmailChange
from core.models.user import User
from core.utils.email_token_sender import send_email_token


class EmailChangeService:
    @staticmethod
    def request_change(user: User, new_email: str) -> None:
        new_email = new_email.strip().lower()
        if User.objects.filter(email__iexact=new_email).exclude(pk=user.pk).exists():
            raise serializers.ValidationError(
                {"new_email": "This e-mail is already in use."}
            )

        raw_code = f"{secrets.randbelow(1000000):06d}"
        try:
            with transaction.atomic():
                EmailChange.objects.filter(user=user).delete()
                change_code = EmailChange(user=user, new_email=new_email)
                change_code.set_code(raw_code)
                change_code.save()
                send_email_token(new_email, raw_code, "Confirm your new e-mail address")
        except Exception:
            raise exceptions.APIException("Service temporarily unavailable.")

    @staticmethod
    def verify_code(user: User, code: str) -> bool:
        change_code = EmailChange.objects.filter(user=user).first()
        if not change_code or not change_code.verify(code):
            raise serializers.ValidationError(
                {"code": "Invalid or expired verification code."}
            )
        return True

    @staticmethod
    def confirm_change(user: User, code: str, current_password: str) -> None:
        if not user.check_password(current_password):
            raise serializers.ValidationError({"password": "Invalid current password."})

        EmailChangeService.verify_code(user, code)

        change_code = EmailChange.objects.get(user=user)
        user.email = change_code.new_email
        user.save(update_fields=["email", "updated_at"])

        change_code.mark_used()
