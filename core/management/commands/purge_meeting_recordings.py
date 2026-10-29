from django.core.management.base import BaseCommand

from core.modules.meetings.services.meetings import RecordingService, retention_days


class Command(BaseCommand):
    help = "Deletes meeting recordings older than MEETING_RECORDING_RETENTION_DAYS."

    def handle(self, *args, **options):
        count = RecordingService.purge_expired()
        self.stdout.write(
            f"{count} recording(s) older than {retention_days()} days deleted."
        )
