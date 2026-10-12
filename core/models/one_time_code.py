from datetime import timedelta
from typing import ClassVar

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

CODE_LIFETIME = timedelta(minutes=15)
MAX_ATTEMPTS = 5


def default_expiry() -> timezone.datetime:
    return timezone.now() + CODE_LIFETIME


class OneTimeCode(models.Model):
    CODE_LIFETIME: ClassVar[timedelta] = CODE_LIFETIME
    MAX_ATTEMPTS: ClassVar[int] = MAX_ATTEMPTS

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(class)s",
        verbose_name=_("user"),
    )
    code = models.CharField(
        _("hashed code"),
        max_length=128,
    )
    used = models.BooleanField(
        _("used"),
        default=False,
        db_index=True,
    )
    used_at = models.DateTimeField(
        _("used at"),
        null=True,
        blank=True,
    )
    attempts = models.PositiveSmallIntegerField(
        _("attempts"),
        default=0,
    )
    created_at = models.DateTimeField(
        _("created at"),
        auto_now_add=True,
        db_index=True,
    )
    expires_at = models.DateTimeField(
        _("expires at"),
        default=default_expiry,
        db_index=True,
    )

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    def set_code(self, raw_code):
        self.code = make_password(raw_code)

    def check_code(self, raw_code):
        return check_password(raw_code, self.code)

    def mark_used(self):
        self.used = True
        self.used_at = timezone.now()
        self.save(update_fields=["used", "used_at"])

    def register_failure(self):
        type(self).objects.filter(pk=self.pk).update(attempts=models.F("attempts") + 1)
        self.refresh_from_db(fields=["attempts"])

        exhausted = self.attempts >= self.MAX_ATTEMPTS
        if exhausted and not self.used:
            self.mark_used()

        return exhausted

    def verify(self, raw_code):
        if not self.is_valid:
            return False

        if not self.check_code(raw_code):
            self.register_failure()
            return False

        return True

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_exhausted(self):
        return self.attempts >= self.MAX_ATTEMPTS

    @property
    def is_valid(self):
        return (
            not self.used
            and self.used_at is None
            and not self.is_expired
            and not self.is_exhausted
        )
