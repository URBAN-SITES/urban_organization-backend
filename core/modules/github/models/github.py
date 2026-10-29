import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models.fields import EncryptedTextField
from core.modules.kanban.models.sector import Sector
from core.modules.kanban.models.task import Task


class GitHubIdentity(models.Model):
    """The GitHub account a user logs in with. Holds no token."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="github_identity",
        verbose_name=_("user"),
    )
    github_id = models.BigIntegerField(_("GitHub id"), unique=True)
    login = models.CharField(_("login"), max_length=100)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("GitHub identity")
        verbose_name_plural = _("GitHub identities")

    def __str__(self):
        return self.login


class GitHubConnection(models.Model):
    """User-to-server token of the GitHub App, used to list the user's repositories."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="github_connection",
        verbose_name=_("user"),
    )
    github_id = models.BigIntegerField(_("GitHub id"))
    login = models.CharField(_("login"), max_length=100)
    avatar_url = models.URLField(_("avatar url"), blank=True)
    access_token = EncryptedTextField(_("access token"))
    refresh_token = EncryptedTextField(_("refresh token"), blank=True)
    expires_at = models.DateTimeField(_("expires at"), null=True, blank=True)
    refresh_expires_at = models.DateTimeField(
        _("refresh expires at"), null=True, blank=True
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("GitHub connection")
        verbose_name_plural = _("GitHub connections")

    def __str__(self):
        return self.login


class ProjectRepository(models.Model):
    """A GitHub repository associated with a project (sector). Unlinking never touches GitHub."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sector = models.ForeignKey(
        Sector,
        on_delete=models.CASCADE,
        related_name="repositories",
        verbose_name=_("sector"),
    )
    github_id = models.BigIntegerField(_("GitHub id"))
    installation_id = models.BigIntegerField(_("installation id"))
    full_name = models.CharField(_("full name"), max_length=200)
    private = models.BooleanField(_("private"), default=False)
    html_url = models.URLField(_("url"))
    default_branch = models.CharField(_("default branch"), max_length=255, blank=True)
    language = models.CharField(_("language"), max_length=60, blank=True)
    linked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        verbose_name=_("linked by"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("project repository")
        verbose_name_plural = _("project repositories")
        ordering = ["full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["sector", "github_id"], name="unique_repository_per_sector"
            )
        ]

    def __str__(self):
        return self.full_name


class TaskGitHubLink(models.Model):
    """A branch or pull request linked to a task; webhooks keep its state fresh."""

    class Kind(models.TextChoices):
        BRANCH = "branch", _("branch")
        PULL = "pull", _("pull request")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="github_links",
        verbose_name=_("task"),
    )
    repository = models.ForeignKey(
        ProjectRepository,
        on_delete=models.CASCADE,
        related_name="task_links",
        verbose_name=_("repository"),
    )
    kind = models.CharField(_("kind"), max_length=10, choices=Kind)
    ref = models.CharField(_("branch or number"), max_length=255)
    title = models.CharField(_("title"), max_length=500, blank=True)
    state = models.CharField(_("state"), max_length=20, blank=True)
    html_url = models.URLField(_("url"))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        verbose_name=_("created by"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("task GitHub link")
        verbose_name_plural = _("task GitHub links")
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["task", "repository", "kind", "ref"],
                name="unique_github_link_per_task",
            )
        ]

    def __str__(self):
        return f"{self.kind}:{self.ref}"
