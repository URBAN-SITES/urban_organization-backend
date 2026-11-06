from django.contrib import admin

from core.modules.calls.models.call import Call, CallParticipant


class CallParticipantInline(admin.TabularInline):
    model = CallParticipant
    extra = 0
    readonly_fields = ("user", "state", "joined_at", "left_at")


@admin.register(Call)
class CallAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "status", "channel", "started_by", "created_at")
    list_filter = ("kind", "status", "created_at")
    inlines = [CallParticipantInline]
