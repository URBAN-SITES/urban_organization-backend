import hashlib

from django.core.cache import cache
from django.http import HttpResponse, JsonResponse

from core.response_messages import MSG_IDEMPOTENCY_IN_PROGRESS
from core.utils.cookies import get_auth_cookie_name

IDEMPOTENCY_HEADER = "Idempotency-Key"
IDEMPOTENCY_TTL = 60 * 60 * 24  # 24h
IDEMPOTENT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class IdempotencyMiddleware:
    """
    Client sends `Idempotency-Key: <uuid>` on a write request; retries with the
    same key get the first response replayed instead of running the action again
    (e.g. double-click on "pay"). Requests without the header are untouched.
    Needs a shared cache (Redis) when running more than one process.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        key = request.headers.get(IDEMPOTENCY_HEADER)
        if not key or request.method not in IDEMPOTENT_METHODS:
            return self.get_response(request)

        # scope the key to the caller so it cannot replay someone else's response
        caller = request.COOKIES.get(get_auth_cookie_name()) or request.META.get(
            "REMOTE_ADDR", ""
        )
        digest = hashlib.sha256(
            f"{caller}:{request.method}:{request.path}:{key}".encode()
        ).hexdigest()
        cache_key, lock_key = f"idempotency:{digest}", f"idempotency-lock:{digest}"

        if cached := cache.get(cache_key):
            status, content, content_type = cached
            response = HttpResponse(content, status=status, content_type=content_type)
            response["Idempotent-Replayed"] = "true"
            return response

        if not cache.add(lock_key, True, timeout=60):
            return JsonResponse(
                {"detail": str(MSG_IDEMPOTENCY_IN_PROGRESS)},
                status=409,
            )
        try:
            response = self.get_response(request)
            if response.status_code < 500:
                cache.set(
                    cache_key,
                    (response.status_code, response.content, response["Content-Type"]),
                    IDEMPOTENCY_TTL,
                )
            return response
        finally:
            cache.delete(lock_key)
