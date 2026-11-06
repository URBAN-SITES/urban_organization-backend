"""Voice/video calls in chat channels: ringing, joining and the WebRTC signaling relay.

Client flow (WebRTC "mesh": every participant connects to every other one):
  1. POST /calls/ {"channel_id", "kind": "video"} -> the others get `call.ringing`.
  2. Whoever answers calls POST /calls/<id>/join/ (or sends {"type": "call.join"} on the
     socket) and gets the call with who is already in. The newcomer creates one
     RTCPeerConnection per person already in and sends each an offer with
     {"type": "call.signal", "call_id", "to_user_id", "data": {"sdp": ...}}.
  3. Answers and ICE candidates go back the same way; the server only relays them.
  4. Screen sharing = getDisplayMedia() + replaceTrack(); tell the others with
     POST /calls/<id>/media/ {"screen_sharing": true}.
  5. leave / decline; the call ends when nobody is left (a direct call when one side
     leaves) and a summary message lands in the channel.
ICE servers (public STUN, plus your own TURN when set) come from GET /calls/ice-servers/.
"""

import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from core.models.user import User
from core.modules.calls.models.call import Call, CallParticipant
from core.modules.calls.response_messages import (
    MSG_CALL_IN_PROGRESS,
    MSG_CALL_NO_ONE,
    MSG_CALL_NOT_FOUND,
    MSG_CALL_TOO_BIG,
    MSG_NOT_IN_CALL,
    MSG_SIGNAL_TOO_BIG,
)
from core.websockets.consumers import send_to_user

MAX_SIGNAL_BYTES = 64 * 1024
MEDIA_FLAGS = ("muted", "video_off", "screen_sharing")
LIVE = (Call.Status.RINGING, Call.Status.ONGOING)


def participant_payload(p: CallParticipant) -> dict:
    return {
        "user_id": str(p.user_id),
        "name": p.user.name,
        "state": p.state,
        **{flag: getattr(p, flag) for flag in MEDIA_FLAGS},
    }


def call_payload(call: Call) -> dict:
    return {
        "id": str(call.id),
        "channel_id": str(call.channel_id),
        "organization_id": str(call.channel.organization_id),
        "kind": call.kind,
        "status": call.status,
        "started_by": (
            {"id": str(call.started_by_id), "name": call.started_by.name}
            if call.started_by_id
            else None
        ),
        "participants": [
            participant_payload(p)
            for p in call.participants.select_related("user").order_by("id")
        ],
        "created_at": call.created_at.isoformat(),
        "answered_at": call.answered_at.isoformat() if call.answered_at else None,
        "ended_at": call.ended_at.isoformat() if call.ended_at else None,
        "duration_seconds": call.duration_seconds,
    }


def _push(call: Call, payload: dict, skip=None) -> None:
    """Sends to every participant once the transaction commits."""
    ids = list(call.participants.values_list("user_id", flat=True))

    def send():
        for user_id in ids:
            if user_id != skip:
                send_to_user(user_id, payload)

    transaction.on_commit(send)


def _summary(call: Call, status: str) -> str:
    video = call.kind == Call.Kind.VIDEO
    if status == Call.Status.MISSED:
        return _("Missed video call") if video else _("Missed voice call")
    if status == Call.Status.DECLINED:
        return _("Video call declined") if video else _("Voice call declined")
    minutes = max(1, round(call.duration_seconds / 60))
    text = _("Video call") if video else _("Voice call")
    return f"{text} · {minutes} min"


class CallService:
    @staticmethod
    def get_for(user: User, call_id) -> Call:
        """Only the people the call rang can see it (404 for anyone else)."""
        try:
            call_id = uuid.UUID(str(call_id))
        except ValueError:  # malformed id from a client
            raise NotFound(MSG_CALL_NOT_FOUND)
        call = (
            Call.objects.filter(pk=call_id, participants__user=user)
            .select_related("started_by", "channel")
            .first()
        )
        if call is None:
            raise NotFound(MSG_CALL_NOT_FOUND)
        return call

    @staticmethod
    def history(user: User, limit: int = 100) -> list[Call]:
        return list(
            Call.objects.filter(participants__user=user).select_related(
                "started_by", "channel"
            )[:limit]
        )

    @staticmethod
    def _live_for(user: User, call_id) -> tuple[Call, CallParticipant]:
        call = CallService.get_for(user, call_id)
        CallService.expire_unanswered(call)
        if not call.is_live:
            raise NotFound(MSG_CALL_NOT_FOUND)
        return call, call.participants.get(user=user)

    @staticmethod
    @transaction.atomic
    def start(user: User, channel_id, kind: str = Call.Kind.AUDIO) -> Call:
        from core.modules.chat.services.chat import ChatService
        from core.modules.notifications.services.notification import (
            NotificationService,
        )

        channel = ChatService.get_channel(user, channel_id)  # 404 without access
        for live in channel.calls.filter(status__in=LIVE):
            CallService.expire_unanswered(live)
            if live.is_live:
                raise ValidationError(
                    {"call_id": str(live.id), "detail": MSG_CALL_IN_PROGRESS}
                )
        others = list(
            User.objects.filter(
                id__in=ChatService._recipients(channel), is_active=True
            ).exclude(pk=user.pk)
        )
        if not others:
            raise ValidationError(MSG_CALL_NO_ONE)
        if len(others) + 1 > settings.CALL_MAX_PARTICIPANTS:
            raise ValidationError(
                MSG_CALL_TOO_BIG % {"max": settings.CALL_MAX_PARTICIPANTS}
            )
        now = timezone.now()
        call = Call.objects.create(channel=channel, started_by=user, kind=kind)
        CallParticipant.objects.bulk_create(
            [
                CallParticipant(
                    call=call,
                    user=user,
                    state=CallParticipant.State.JOINED,
                    joined_at=now,
                    video_off=kind == Call.Kind.AUDIO,
                )
            ]
            + [CallParticipant(call=call, user=other) for other in others]
        )
        _push(call, {"type": "call.ringing", "call": call_payload(call)}, skip=user.pk)
        title = (
            _("Video call from %(name)s")
            if kind == Call.Kind.VIDEO
            else _("Voice call from %(name)s")
        ) % {"name": user.get_short_name()}
        for other in others:
            # a push also rings the phone when the app is in the background
            NotificationService.notify(
                other,
                title,
                channel.name,
                {
                    "event": "call.incoming",
                    "call_id": str(call.id),
                    "channel_id": str(channel.id),
                    "organization_id": str(channel.organization_id),
                    "kind": kind,
                },
            )
        return call

    @staticmethod
    @transaction.atomic
    def join(user: User, call_id) -> Call:
        call, me = CallService._live_for(user, call_id)
        now = timezone.now()
        me.state = CallParticipant.State.JOINED
        me.joined_at = now
        me.left_at = None
        me.save(update_fields=["state", "joined_at", "left_at"])
        if call.status == Call.Status.RINGING:
            call.status = Call.Status.ONGOING
            call.answered_at = now
            call.save(update_fields=["status", "answered_at"])
        _push(
            call,
            {
                "type": "call.participant_joined",
                "call_id": str(call.id),
                "participant": participant_payload(me),
            },
            skip=user.pk,
        )
        return call

    @staticmethod
    @transaction.atomic
    def decline(user: User, call_id) -> Call:
        call, me = CallService._live_for(user, call_id)
        if me.state != CallParticipant.State.INVITED:
            raise PermissionDenied(MSG_NOT_IN_CALL)
        me.state = CallParticipant.State.DECLINED
        me.save(update_fields=["state"])
        _push(
            call,
            {"type": "call.declined", "call_id": str(call.id), "user_id": str(user.pk)},
            skip=user.pk,
        )
        CallService._end_if_empty(call)
        return call

    @staticmethod
    @transaction.atomic
    def leave(user: User, call_id) -> Call:
        call, me = CallService._live_for(user, call_id)
        if me.state != CallParticipant.State.JOINED:
            raise PermissionDenied(MSG_NOT_IN_CALL)
        me.state = CallParticipant.State.LEFT
        me.left_at = timezone.now()
        for flag in MEDIA_FLAGS:
            setattr(me, flag, False)
        me.save()
        _push(
            call,
            {
                "type": "call.participant_left",
                "call_id": str(call.id),
                "user_id": str(user.pk),
            },
            skip=user.pk,
        )
        CallService._end_if_empty(call)
        return call

    @staticmethod
    def leave_all(user: User) -> int:
        """When the user's last socket closes (tab closed, network gone)."""
        live = Call.objects.filter(
            participants__user=user,
            participants__state=CallParticipant.State.JOINED,
            status__in=LIVE,
        ).distinct()
        count = 0
        for call in live:
            try:
                CallService.leave(user, call.pk)
                count += 1
            except NotFound:  # ended meanwhile
                pass
        return count

    @staticmethod
    def _end_if_empty(call: Call) -> None:
        joined = call.participants.filter(state=CallParticipant.State.JOINED).count()
        if call.status == Call.Status.RINGING:
            waiting = call.participants.filter(
                state=CallParticipant.State.INVITED
            ).count()
            if joined == 0:  # the caller hung up before anyone answered
                CallService.end(call, Call.Status.MISSED)
            elif waiting == 0:  # everybody declined
                CallService.end(call, Call.Status.DECLINED)
            return
        from core.modules.chat.models.chat import ChatChannel

        # a direct call ends when one side leaves; a group call when the last one leaves
        is_direct = call.channel.kind == ChatChannel.Kind.DIRECT
        if joined == 0 or (joined == 1 and is_direct):
            CallService.end(call, Call.Status.ENDED)

    @staticmethod
    @transaction.atomic
    def end(call: Call, status: str = Call.Status.ENDED) -> None:
        from core.modules.chat.models.chat import ChatMessage
        from core.modules.chat.services.chat import ChatService
        from core.modules.notifications.services.notification import (
            NotificationService,
        )

        call = (
            Call.objects.select_for_update().select_related("channel").get(pk=call.pk)
        )
        if not call.is_live:  # another request ended it first
            return
        now = timezone.now()
        call.status = status
        call.ended_at = now
        call.save(update_fields=["status", "ended_at"])
        call.participants.filter(state=CallParticipant.State.JOINED).update(
            state=CallParticipant.State.LEFT, left_at=now
        )
        _push(call, {"type": "call.ended", "call_id": str(call.id), "status": status})
        if call.started_by_id:
            # summary in the channel; no notification (the ring already was one)
            message = ChatMessage.objects.create(
                channel=call.channel,
                author_id=call.started_by_id,
                content=_summary(call, status),
                call=call,
            )
            ChatService._broadcast(call.channel, "chat.message", message)
        if status == Call.Status.MISSED:
            caller = call.started_by.get_short_name() if call.started_by_id else ""
            for p in call.participants.filter(
                state=CallParticipant.State.INVITED
            ).select_related("user"):
                NotificationService.notify(
                    p.user,
                    _("Missed call"),
                    caller,
                    {
                        "event": "call.missed",
                        "call_id": str(call.id),
                        "channel_id": str(call.channel_id),
                        "organization_id": str(call.channel.organization_id),
                    },
                )

    @staticmethod
    def expire_unanswered(call: Call | None = None) -> int:
        """Ringing calls nobody answered within CALL_RING_SECONDS become missed; calls
        left "ongoing" by crashed clients close after CALL_MAX_HOURS. Without `call`
        it sweeps every call (Celery beat, every minute)."""
        cutoff = timezone.now() - timedelta(seconds=settings.CALL_RING_SECONDS)
        if call is not None:
            if call.status == Call.Status.RINGING and call.created_at < cutoff:
                CallService.end(call, Call.Status.MISSED)
                call.refresh_from_db()
                return 1
            return 0
        stale = list(
            Call.objects.filter(status=Call.Status.RINGING, created_at__lt=cutoff)
        )
        for row in stale:
            CallService.end(row, Call.Status.MISSED)
        old = timezone.now() - timedelta(hours=settings.CALL_MAX_HOURS)
        for row in Call.objects.filter(status=Call.Status.ONGOING, created_at__lt=old):
            CallService.end(row, Call.Status.ENDED)
        return len(stale)

    @staticmethod
    def signal(user: User, call_id, to_user_id, data) -> None:
        """Relays an SDP offer/answer or ICE candidate to one other person in the call."""
        if not isinstance(data, dict):
            raise ValidationError(MSG_SIGNAL_TOO_BIG)
        if len(json.dumps(data)) > MAX_SIGNAL_BYTES:
            raise ValidationError(MSG_SIGNAL_TOO_BIG)
        call, me = CallService._live_for(user, call_id)
        if me.state != CallParticipant.State.JOINED:
            raise PermissionDenied(MSG_NOT_IN_CALL)
        try:
            to_user_id = uuid.UUID(str(to_user_id))
        except ValueError:
            raise NotFound(MSG_NOT_IN_CALL)
        target = call.participants.filter(
            user_id=to_user_id, state=CallParticipant.State.JOINED
        ).first()
        if target is None or target.user_id == user.pk:
            raise NotFound(MSG_NOT_IN_CALL)
        send_to_user(
            target.user_id,
            {
                "type": "call.signal",
                "call_id": str(call.id),
                "from_user_id": str(user.pk),
                "data": data,
            },
        )

    @staticmethod
    @transaction.atomic
    def media(user: User, call_id, flags: dict) -> CallParticipant:
        call, me = CallService._live_for(user, call_id)
        if me.state != CallParticipant.State.JOINED:
            raise PermissionDenied(MSG_NOT_IN_CALL)
        for flag in MEDIA_FLAGS:
            if flag in flags:
                setattr(me, flag, bool(flags[flag]))
        me.save(update_fields=list(MEDIA_FLAGS))
        _push(
            call,
            {
                "type": "call.media",
                "call_id": str(call.id),
                "participant": participant_payload(me),
            },
            skip=user.pk,
        )
        return me

    @staticmethod
    def ice_servers(user: User) -> list[dict]:
        """Free public STUN by default. For people behind strict networks add your own
        TURN (coturn) with `use-auth-secret`; credentials expire in a day."""
        servers = [{"urls": url} for url in settings.ICE_STUN_URLS]
        if settings.TURN_URLS and settings.TURN_SECRET:
            username = f"{int(time.time()) + 24 * 3600}:{user.pk}"
            digest = hmac.new(
                settings.TURN_SECRET.encode(), username.encode(), hashlib.sha1
            ).digest()
            servers.append(
                {
                    "urls": settings.TURN_URLS,
                    "username": username,
                    "credential": base64.b64encode(digest).decode(),
                }
            )
        return servers
