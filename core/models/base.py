import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class BaseModel(models.Model):
    """
    Inherit from this in every new model: UUID pk, timestamps, soft delete
    and an owner. Pair it with core.views.base.OwnedModelViewSet for CRUD.

        class Product(BaseModel):
            name = models.CharField(max_length=255)
            extra = models.JSONField(default=dict, blank=True)  # free-form fields
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="+",
        verbose_name=_("owner"),
    )
    is_active = models.BooleanField(_("active"), default=True, db_index=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    def soft_delete(self):
        self.is_active = False
        self.save(update_fields=["is_active", "updated_at"])
