import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Call(models.Model):
    """A voice or video call inside a chat channel (WebRTC, peer to peer).

    The server only rings people and relays the WebRTC handshake (signaling); audio and
    video flow directly between the browsers. Large meetings stay on LiveKit (meetings)."""

    class Kind(models.TextChoices):
        AUDIO = "audio", _("voice")
        VIDEO = "video", _("video")

    class Status(models.TextChoices):
        RINGING = "ringing", _("ringing")
        ONGOING = "ongoing", _("ongoing")
        ENDED = "ended", _("ended")
        MISSED = "missed", _("missed")
        DECLINED = "declined", _("declined")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    channel = models.ForeignKey(
        "core.ChatChannel",
        on_delete=models.CASCADE,
        related_name="calls",
        verbose_name=_("channel"),
    )
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        verbose_name=_("started by"),
    )
    kind = models.CharField(_("kind"), max_length=5, choices=Kind, default=Kind.AUDIO)
    status = models.CharField(
        _("status"), max_length=8, choices=Status, default=Status.RINGING, db_index=True
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    answered_at = models.DateTimeField(_("answered at"), null=True, blank=True)
    ended_at = models.DateTimeField(_("ended at"), null=True, blank=True)

    class Meta:
        verbose_name = _("call")
        verbose_name_plural = _("calls")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.created_at:%Y-%m-%d %H:%M}"

    @property
    def is_live(self) -> bool:
        return self.status in (self.Status.RINGING, self.Status.ONGOING)

    @property
    def duration_seconds(self) -> int:
        if not self.answered_at or not self.ended_at:
            return 0
        return int((self.ended_at - self.answered_at).total_seconds())


class CallParticipant(models.Model):
    class State(models.TextChoices):
        INVITED = "invited", _("invited")
        JOINED = "joined", _("in the call")
        DECLINED = "declined", _("declined")
        LEFT = "left", _("left")

    call = models.ForeignKey(
        Call,
        on_delete=models.CASCADE,
        related_name="participants",
        verbose_name=_("call"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="call_participations",
        verbose_name=_("user"),
    )
    state = models.CharField(
        _("state"), max_length=8, choices=State, default=State.INVITED
    )
    joined_at = models.DateTimeField(_("joined at"), null=True, blank=True)
    left_at = models.DateTimeField(_("left at"), null=True, blank=True)
    # what the others should show: muted mic, camera off, sharing screen
    muted = models.BooleanField(_("muted"), default=False)
    video_off = models.BooleanField(_("camera off"), default=False)
    screen_sharing = models.BooleanField(_("sharing screen"), default=False)

    class Meta:
        verbose_name = _("call participant")
        verbose_name_plural = _("call participants")
        constraints = [
            models.UniqueConstraint(
                fields=["call", "user"], name="unique_call_participant"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} in {self.call}"
