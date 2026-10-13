import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Payment(models.Model):
    class Status(models.TextChoices):
        # same values Mercado Pago uses, so its status is stored as-is
        PENDING = "pending", _("pending")
        APPROVED = "approved", _("approved")
        IN_PROCESS = "in_process", _("in process")
        REJECTED = "rejected", _("rejected")
        CANCELLED = "cancelled", _("cancelled")
        REFUNDED = "refunded", _("refunded")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name=_("user"),
    )
    title = models.CharField(_("title"), max_length=255)
    amount = models.DecimalField(_("amount"), max_digits=10, decimal_places=2)
    status = models.CharField(
        _("status"), max_length=20, choices=Status, default=Status.PENDING
    )
    preference_id = models.CharField(_("preference id"), max_length=255, blank=True)
    provider_payment_id = models.CharField(
        _("provider payment id"), max_length=255, blank=True
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("payment")
        verbose_name_plural = _("payments")
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="payment_amount_positive"
            )
        ]

    def __str__(self) -> str:
        return f"{self.title} - {self.amount} ({self.status})"
