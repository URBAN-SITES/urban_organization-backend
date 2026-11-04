import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.modules.kanban.models.sector import Sector


class Page(models.Model):
    """A document of a sector (wiki): notes, specs, decisions, in Markdown."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sector = models.ForeignKey(
        Sector,
        on_delete=models.CASCADE,
        related_name="pages",
        verbose_name=_("sector"),
    )
    title = models.CharField(_("title"), max_length=200)
    content = models.TextField(_("content"), blank=True)
    is_pinned = models.BooleanField(_("pinned"), default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        verbose_name=_("created by"),
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        verbose_name=_("updated by"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("page")
        verbose_name_plural = _("pages")
        ordering = ["-is_pinned", "-updated_at"]

    def __str__(self) -> str:
        return self.title
