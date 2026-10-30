from datetime import timedelta

from django.conf import settings

SESSION_ONLY_COOKIE = "session_only"


def get_auth_cookie_kwargs(is_refresh=False, persistent=True):
    lifetime: timedelta = (
        settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]
        if is_refresh
        else settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]
    )

    return {
        # without max_age the browser drops the cookie when it closes ("remember me" off)
        "max_age": int(lifetime.total_seconds()) if persistent else None,
        "httponly": settings.SIMPLE_JWT.get("AUTH_COOKIE_HTTP_ONLY", True),
        "secure": settings.SIMPLE_JWT.get("AUTH_COOKIE_SECURE", False),
        "path": settings.SIMPLE_JWT.get("AUTH_COOKIE_PATH", "/"),
        "samesite": settings.SIMPLE_JWT.get("AUTH_COOKIE_SAMESITE", "Lax"),
    }


def get_auth_cookie_name():
    return settings.SIMPLE_JWT.get("AUTH_COOKIE", "access_token")


def is_persistent_session(request) -> bool:
    """False while the browser carries the marker of a login without "remember me"."""
    return request.COOKIES.get(SESSION_ONLY_COOKIE) != "1"


def set_auth_cookies(response, tokens, persistent=True):
    response.set_cookie(
        get_auth_cookie_name(),
        tokens["access"],
        **get_auth_cookie_kwargs(persistent=persistent),
    )
    response.set_cookie(
        "refresh_token",
        tokens["refresh"],
        **get_auth_cookie_kwargs(is_refresh=True, persistent=persistent),
    )
    if persistent:
        response.delete_cookie(SESSION_ONLY_COOKIE, **get_delete_cookie_kwargs())
    else:
        # the refresh view reads this marker to keep renewed cookies session-only too
        response.set_cookie(
            SESSION_ONLY_COOKIE, "1", **get_auth_cookie_kwargs(persistent=False)
        )


def get_delete_cookie_kwargs():
    cookie_kwargs = get_auth_cookie_kwargs()
    return {
        "path": cookie_kwargs.get("path", "/"),
        "domain": cookie_kwargs.get("domain", None),
        "samesite": cookie_kwargs.get("samesite", "Lax"),
    }
