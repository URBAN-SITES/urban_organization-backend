from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


# [P2-C] Created lazily (get_or_create) the first time the user opens settings.
class UserSettings(models.Model):
    class Theme(models.TextChoices):
        LIGHT = "light", _("light")
        DARK = "dark", _("dark")
        SYSTEM = "system", _("system")

    class DateFormat(models.TextChoices):
        DAY_FIRST = "dd/mm/yyyy", _("day/month/year")
        ISO = "yyyy-mm-dd", _("year-month-day")
        LONG = "long", _("long date")

    class WeekStart(models.TextChoices):
        SUNDAY = "sunday", _("Sunday")
        MONDAY = "monday", _("Monday")

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="settings",
        verbose_name=_("user"),
    )
    theme = models.CharField(
        _("theme"), max_length=10, choices=Theme, default=Theme.SYSTEM
    )
    locale = models.CharField(_("locale"), max_length=10, default="pt-BR")
    timezone = models.CharField(
        _("timezone"), max_length=64, default="America/Sao_Paulo"
    )
    push_enabled = models.BooleanField(_("push enabled"), default=True)
    email_product = models.BooleanField(_("product e-mails"), default=True)
    email_weekly_digest = models.BooleanField(_("weekly digest"), default=False)
    email_security = models.BooleanField(_("security e-mails"), default=True)
    email_assigned = models.BooleanField(_("assignment e-mails"), default=True)
    email_mentions = models.BooleanField(_("mention e-mails"), default=True)
    email_deadlines = models.BooleanField(_("deadline e-mails"), default=True)
    app_comments = models.BooleanField(_("comment notifications"), default=True)
    app_status = models.BooleanField(_("status notifications"), default=True)
    app_ai = models.BooleanField(_("AI notifications"), default=False)
    date_format = models.CharField(
        _("date format"),
        max_length=10,
        choices=DateFormat,
        default=DateFormat.DAY_FIRST,
    )
    week_start = models.CharField(
        _("week start"), max_length=6, choices=WeekStart, default=WeekStart.SUNDAY
    )
    compact_cards = models.BooleanField(_("compact cards"), default=False)
    show_completed = models.BooleanField(_("show completed tasks"), default=True)

    class Meta:
        verbose_name = _("user settings")
        verbose_name_plural = _("user settings")

    def __str__(self) -> str:
        return f"Settings of {self.user}"
