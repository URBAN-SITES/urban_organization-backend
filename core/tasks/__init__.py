# Celery autodiscovers `core.tasks`; import each task module here
from core.modules.meetings.tasks import (
    process_meeting_insight as process_meeting_insight,
)
from core.tasks.email import send_email_task as send_email_task
