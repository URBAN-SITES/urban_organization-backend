import os

from celery import Celery

# worker (with the periodic jobs): celery -A app worker --beat -l info
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings.dev")

app = Celery("app")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
