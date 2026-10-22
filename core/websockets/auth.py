from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework.exceptions import APIException

from core.authenticate import CustomAuthentication
from core.utils.cookies import get_auth_cookie_name


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


class JWTCookieAuthMiddleware(BaseMiddleware):
    """Sets scope["user"] from the access-token cookie sent on the handshake."""

    async def __call__(self, scope, receive, send):
        raw_token = scope.get("cookies", {}).get(get_auth_cookie_name())
        scope["user"] = (
            await get_user_from_token(raw_token) if raw_token else AnonymousUser()
        )
        return await super().__call__(scope, receive, send)
