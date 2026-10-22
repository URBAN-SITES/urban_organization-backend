import os

from .base import *  # noqa: F403

DEBUG = True
DEBUG_PROPAGATE_EXCEPTIONS = False
ALLOWED_HOSTS = []
SECRET_KEY = os.getenv("SECRET_KEY")
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
        "ATOMIC_REQUESTS ": True,
        "TIME_ZONE": "UTC",
        # AUTOCOMMIT
        # ENGINE
        # HOST
        # NAME
        # CONN_MAX_AGE
        # CONN_HEALTH_CHECKS
        # OPTIONS
        # PASSWORD
        # PORT
        # DISABLE_SERVER_SIDE_CURSORS
        # USER
        # TEST
        # CHARSET
        # COLLATION
        # DEPENDENCIES
        # MIGRATE
        # MIRROR
        # NAME
        # TEMPLATE
        # CREATE_DB
        # CREATE_USER
        # USER
        # PASSWORD
        # ORACLE_MANAGED_FILES
        # TBLSPACE
        # TBLSPACE_TMP
        # DATAFILE
        # DATAFILE_TMP
        # DATAFILE_MAXSIZE
        # DATAFILE_TMP_MAXSIZE
        # DATAFILE_SIZE
        # DATAFILE_TMP_SIZE
        # DATAFILE_EXTSIZE
        # DATAFILE_TMP_EXTSIZE
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
