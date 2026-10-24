import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.modules.kanban.models.task import Task
from core.modules.organizations.models.organization import Organization
from core.modules.payments.models.payment import Payment


# Fundraiser ("vaquinha") of an organization. The money is a regular Payment
# (Mercado Pago PIX); `raised` is always the sum of its approved payments.
class Campaign(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", _("active")
        CLOSED = "closed", _("closed")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="campaigns",
        verbose_name=_("organization"),
    )
    # set when the fundraiser is a charge attached to a task
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="campaigns",
        verbose_name=_("task"),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("created by"),
    )
    title = models.CharField(_("title"), max_length=255)
    description = models.TextField(_("description"), blank=True)
    goal_amount = models.DecimalField(_("goal amount"), max_digits=10, decimal_places=2)
    deadline = models.DateField(_("deadline"), null=True, blank=True)
    status = models.CharField(
        _("status"), max_length=10, choices=Status, default=Status.ACTIVE
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("campaign")
        verbose_name_plural = _("campaigns")
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(goal_amount__gt=0), name="campaign_goal_positive"
            )
        ]

    def __str__(self) -> str:
        return self.title


class Contribution(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="contributions",
        verbose_name=_("campaign"),
    )
    payment = models.OneToOneField(
        Payment,
        on_delete=models.PROTECT,
        related_name="contribution",
        verbose_name=_("payment"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="contributions",
        verbose_name=_("user"),
    )
    message = models.CharField(_("message"), max_length=255, blank=True)
    anonymous = models.BooleanField(_("anonymous"), default=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("contribution")
        verbose_name_plural = _("contributions")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.campaign} - {self.payment.amount}"
