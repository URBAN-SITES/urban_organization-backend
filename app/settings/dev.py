import os

from .base import *  # noqa: F403

DEBUG = True
DEBUG_PROPAGATE_EXCEPTIONS = False
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",")
SECRET_KEY = os.getenv("SECRET_KEY")
if os.getenv("POSTGRES_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "app"),
            "USER": os.getenv("POSTGRES_USER", "app"),
            "PASSWORD": os.environ["POSTGRES_PASSWORD"],
            "HOST": os.environ["POSTGRES_HOST"],
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
            "TIME_ZONE": "UTC",
            # write transactions take the lock up front, so check-then-insert is safe
            "OPTIONS": {"transaction_mode": "IMMEDIATE"},
        }
    }

# Real SMTP (from base.py) when EMAIL_HOST_USER and EMAIL_HOST_PASSWORD are set in .env;
# otherwise e-mails are printed to the terminal.
if not (os.getenv("EMAIL_HOST_USER") and os.getenv("EMAIL_HOST_PASSWORD")):
    MAILERS = {
        "default": {
            "BACKEND": "django.core.mail.backends.console.EmailBackend",
        },
    }

# run tasks inline and cache in memory so dev works without Redis;
# delete both to test against a real Redis + worker
CELERY_TASK_ALWAYS_EAGER = True
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
