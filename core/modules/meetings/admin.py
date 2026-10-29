from django.contrib import admin

from core.modules.meetings.models.insight import MeetingInsight
from core.modules.meetings.models.meeting import Meeting, MeetingRecording


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ("title", "sector", "starts_at", "ends_at", "created_by")
    list_filter = ("starts_at",)
    search_fields = ("title",)
    raw_id_fields = ("sector", "created_by", "participants")


@admin.register(MeetingRecording)
class MeetingRecordingAdmin(admin.ModelAdmin):
    list_display = ("meeting", "status", "started_at", "duration_seconds")
    list_filter = ("status",)
    raw_id_fields = ("meeting", "started_by")
    readonly_fields = ("egress_id", "file_key", "participants", "error")


@admin.register(MeetingInsight)
class MeetingInsightAdmin(admin.ModelAdmin):
    list_display = ("recording", "status", "attempts", "updated_at")
    list_filter = ("status",)
    raw_id_fields = ("recording",)
    readonly_fields = ("source_key", "segments", "summary", "error")
