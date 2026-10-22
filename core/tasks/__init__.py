# Celery autodiscovers `core.tasks`; import each task module here
from core.tasks.email import send_email_task as send_email_task
