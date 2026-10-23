from django.contrib import admin

from core.modules.kanban.models.resource_link import ResourceLink
from core.modules.kanban.models.sector import Sector, SectorMember
from core.modules.kanban.models.task import ChecklistItem, Comment, Status, Task


class StatusInline(admin.TabularInline):
    model = Status
    extra = 0


class SectorMemberInline(admin.TabularInline):
    model = SectorMember
    extra = 0


@admin.register(Sector)
class SectorAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "is_private", "is_active", "created_at")
    list_filter = ("is_private", "is_active", "created_at")
    search_fields = ("name", "organization__name")
    inlines = [StatusInline, SectorMemberInline]


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "sector", "status", "priority", "assignee", "due_date")
    list_filter = ("priority", "is_active", "status__category")
    search_fields = ("title", "sector__name", "assignee__email")


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("task", "author", "created_at")
    search_fields = ("content", "author__email")


@admin.register(ChecklistItem)
class ChecklistItemAdmin(admin.ModelAdmin):
    list_display = ("content", "task", "is_done")
    list_filter = ("is_done",)
    search_fields = ("content",)


@admin.register(ResourceLink)
class ResourceLinkAdmin(admin.ModelAdmin):
    list_display = ("title", "url", "created_by", "created_at")
    search_fields = ("title", "url")
