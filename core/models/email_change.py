from django.db import models
from django.utils.translation import gettext_lazy as _

from .one_time_code import OneTimeCode


class EmailChange(OneTimeCode):
    """ """

    new_email = models.EmailField(
        _("new email address"),
    )

    class Meta(OneTimeCode.Meta):
        abstract = False
        verbose_name = _("email change code")
        verbose_name_plural = _("email change codes")

    def __str__(self) -> str:
        return f"EmailChange({self.user.email} -> {self.new_email})"
