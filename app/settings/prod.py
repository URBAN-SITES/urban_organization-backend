import os

from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = os.environ["SECRET_KEY"]  # fail fast if missing
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost").split(",")
CSRF_TRUSTED_ORIGINS += [  # noqa: F405
    origin for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if origin
]
# "db" is the Compose service name; outside a container the database is local.
_postgres_host = os.getenv("POSTGRES_HOST", "db")
if _postgres_host == "db" and not os.path.exists("/.dockerenv"):
    _postgres_host = "localhost"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "app"),
        "USER": os.getenv("POSTGRES_USER", "app"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
        "HOST": _postgres_host,
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": int(os.getenv("POSTGRES_CONN_MAX_AGE", "60")),
        "CONN_HEALTH_CHECKS": True,
    }
}
# A transaction-mode pooler (Supabase on port 6543) hands each transaction a different
# server connection: prepared statements and server-side cursors would break there.
if os.getenv("POSTGRES_TRANSACTION_POOLER", "False") == "True":
    DATABASES["default"]["OPTIONS"] = {"prepare_threshold": None}
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True

# The web process and the Celery worker are separate processes: events sent by the worker
# (notifications, meeting updates) only reach open sockets through a shared Redis layer.
if os.getenv("REDIS_URL"):
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [os.environ["REDIS_URL"]]},
        }
    }

# static files served by the app itself (no nginx needed)
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")  # noqa: F405
STATIC_ROOT = BASE_DIR / "staticfiles"  # noqa: F405
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

# set USE_HTTPS=False only to run the container locally over plain http
USE_HTTPS = os.getenv("USE_HTTPS", "True") == "True"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = USE_HTTPS
SESSION_COOKIE_SECURE = USE_HTTPS
CSRF_COOKIE_SECURE = USE_HTTPS
SIMPLE_JWT["AUTH_COOKIE_SECURE"] = USE_HTTPS  # noqa: F405
SECURE_HSTS_SECONDS = 3600 if USE_HTTPS else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = USE_HTTPS
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Free hosting has no separate Celery worker: CELERY_TASK_ALWAYS_EAGER=True runs each task
# inside the web request instead of queueing it. Scheduled jobs (beat) need a worker.
CELERY_TASK_ALWAYS_EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", "False") == "True"
