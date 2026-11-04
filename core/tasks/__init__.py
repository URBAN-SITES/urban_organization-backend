# Celery autodiscovers `core.tasks`; import each task module here
from core.modules.meetings.tasks import (
    process_meeting_insight as process_meeting_insight,
)
from core.tasks.digest import run_scheduled_rules as run_scheduled_rules
from core.tasks.digest import send_digests as send_digests
from core.tasks.email import send_email_task as send_email_task
