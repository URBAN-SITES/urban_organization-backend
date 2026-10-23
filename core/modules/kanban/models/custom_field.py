import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from core.modules.kanban.models.sector import Sector
from core.modules.kanban.models.task import Task


# [P3] Schema only: per-sector custom fields (the "adaptable" part of the product).
class CustomField(models.Model):
    class Type(models.TextChoices):
        TEXT = "text", _("text")
        NUMBER = "number", _("number")
        DATE = "date", _("date")
        SELECT = "select", _("select")
        CHECKBOX = "checkbox", _("checkbox")
        URL = "url", _("url")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sector = models.ForeignKey(
        Sector,
        on_delete=models.CASCADE,
        related_name="custom_fields",
        verbose_name=_("sector"),
    )
    name = models.CharField(_("name"), max_length=100)
    type = models.CharField(_("type"), max_length=10, choices=Type)
    position = models.PositiveIntegerField(_("position"), default=0)

    class Meta:
        verbose_name = _("custom field")
        verbose_name_plural = _("custom fields")
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["sector", "name"], name="unique_custom_field_per_sector"
            )
        ]

    def __str__(self) -> str:
        return self.name


# [P3]
class CustomFieldOption(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    field = models.ForeignKey(
        CustomField,
        on_delete=models.CASCADE,
        related_name="options",
        verbose_name=_("field"),
    )
    name = models.CharField(_("name"), max_length=100)
    color = models.CharField(_("color"), max_length=20, blank=True)
    position = models.PositiveIntegerField(_("position"), default=0)

    class Meta:
        verbose_name = _("custom field option")
        verbose_name_plural = _("custom field options")
        ordering = ["position"]

    def __str__(self) -> str:
        return self.name


# [P3] One typed column is used per field type.
class TaskFieldValue(models.Model):
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="field_values",
        verbose_name=_("task"),
    )
    field = models.ForeignKey(
        CustomField,
        on_delete=models.CASCADE,
        related_name="values",
        verbose_name=_("field"),
    )
    value_text = models.TextField(_("text value"), blank=True)
    value_number = models.DecimalField(
        _("number value"), max_digits=20, decimal_places=6, null=True, blank=True
    )
    value_date = models.DateField(_("date value"), null=True, blank=True)
    value_bool = models.BooleanField(_("boolean value"), null=True, blank=True)
    option = models.ForeignKey(
        CustomFieldOption,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("option"),
    )

    class Meta:
        verbose_name = _("task field value")
        verbose_name_plural = _("task field values")
        constraints = [
            models.UniqueConstraint(
                fields=["task", "field"], name="unique_field_value_per_task"
            )
        ]

    def __str__(self) -> str:
        return f"{self.task} / {self.field}"
