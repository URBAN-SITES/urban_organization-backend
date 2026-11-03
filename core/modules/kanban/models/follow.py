from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.modules.kanban.models.task import Task


class TaskSubscriber(models.Model):
    """Someone who follows a task: notified of comments and status changes."""

    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="subscribers",
        verbose_name=_("task"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="followed_tasks",
        verbose_name=_("user"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("task subscriber")
        verbose_name_plural = _("task subscribers")
        constraints = [
            models.UniqueConstraint(
                fields=["task", "user"], name="unique_task_subscriber"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} -> {self.task}"
