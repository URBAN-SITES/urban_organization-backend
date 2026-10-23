from django.contrib import admin

from core.modules.calendar_sync.models.calendar import (
    TaskCalendarEvent,
    UserIntegration,
)


@admin.register(UserIntegration)
class UserIntegrationAdmin(admin.ModelAdmin):
    list_display = ("user", "provider", "status", "sync_enabled", "expires_at")
    list_filter = ("provider", "status")
    search_fields = ("user__email",)
    exclude = ("access_token", "refresh_token")  # never show credentials


@admin.register(TaskCalendarEvent)
class TaskCalendarEventAdmin(admin.ModelAdmin):
    list_display = ("task", "user", "google_event_id", "last_synced_at")
    search_fields = ("task__title", "user__email")
