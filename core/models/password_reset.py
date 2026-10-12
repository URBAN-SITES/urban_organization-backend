from django.utils.translation import gettext_lazy as _

from .one_time_code import OneTimeCode


class PasswordReset(OneTimeCode):
    class Meta(OneTimeCode.Meta):
        abstract = False
        verbose_name = _("password reset code")
        verbose_name_plural = _("password reset codes")

    def __str__(self) -> str:
        return f"PasswordReset({self.user.email})"
