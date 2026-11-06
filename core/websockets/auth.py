import hashlib
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core import signing
from django.core.cache import cache
from rest_framework.exceptions import APIException

from core.authenticate import CustomAuthentication
from core.utils.cookies import get_auth_cookie_name

TICKET_SALT = "core.websockets.ticket"
TICKET_MAX_AGE = 60


def create_ticket(user) -> str:
    """Short-lived, one-use proof of login for sockets opened on another domain.

    The site and the API can live on different domains (Vercel cannot proxy WebSockets),
    and then the auth cookie never reaches the handshake.
    """
    return signing.dumps(str(user.pk), salt=TICKET_SALT)


@database_sync_to_async
def get_user_from_token(raw_token):
    # same rules as the REST API: valid JWT + active session
    authentication = CustomAuthentication()
    try:
        token = authentication.get_validated_token(raw_token)
        if not authentication.is_session_active(token):
            return AnonymousUser()
        return authentication.get_user(token)
    except APIException:
        return AnonymousUser()


@database_sync_to_async
def get_user_from_ticket(ticket):
    try:
        user_id = signing.loads(ticket, salt=TICKET_SALT, max_age=TICKET_MAX_AGE)
    except signing.BadSignature:  # also covers expired tickets
        return AnonymousUser()
    # the ticket travels in the URL, which proxies log: a second use must fail
    digest = hashlib.sha256(ticket.encode()).hexdigest()
    if not cache.add(f"ws-ticket:{digest}", 1, TICKET_MAX_AGE):
        return AnonymousUser()
    user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
    return user or AnonymousUser()


class JWTCookieAuthMiddleware(BaseMiddleware):
    """Sets scope["user"] from the access-token cookie or a ticket on the handshake."""

    async def __call__(self, scope, receive, send):
        raw_token = scope.get("cookies", {}).get(get_auth_cookie_name())
        ticket = parse_qs(scope.get("query_string", b"").decode()).get("ticket")
        if raw_token:
            scope["user"] = await get_user_from_token(raw_token)
        elif ticket:
            scope["user"] = await get_user_from_ticket(ticket[0])
        else:
            scope["user"] = AnonymousUser()
        return await super().__call__(scope, receive, send)
