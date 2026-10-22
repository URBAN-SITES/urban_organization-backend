from datetime import timedelta

from django.conf import settings


def get_auth_cookie_kwargs(is_refresh=False):
    lifetime: timedelta = (
        settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]
        if is_refresh
        else settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]
    )

    return {
        "max_age": int(lifetime.total_seconds()),
        "httponly": settings.SIMPLE_JWT.get("AUTH_COOKIE_HTTP_ONLY", True),
        "secure": settings.SIMPLE_JWT.get("AUTH_COOKIE_SECURE", False),
        "path": settings.SIMPLE_JWT.get("AUTH_COOKIE_PATH", "/"),
        "samesite": settings.SIMPLE_JWT.get("AUTH_COOKIE_SAMESITE", "Lax"),
    }


def get_auth_cookie_name():
    return settings.SIMPLE_JWT.get("AUTH_COOKIE", "access_token")


def set_auth_cookies(response, tokens):
    response.set_cookie(
        get_auth_cookie_name(), tokens["access"], **get_auth_cookie_kwargs()
    )
    response.set_cookie(
        "refresh_token", tokens["refresh"], **get_auth_cookie_kwargs(is_refresh=True)
    )
