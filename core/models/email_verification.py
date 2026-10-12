from django.utils.translation import gettext_lazy as _

from .one_time_code import OneTimeCode


class EmailVerification(OneTimeCode):
    class Meta(OneTimeCode.Meta):
        abstract = False
        verbose_name = _("email verification code")
        verbose_name_plural = _("email verification codes")

    def __str__(self) -> str:
        return f"EmailVerification({self.user.email})"
