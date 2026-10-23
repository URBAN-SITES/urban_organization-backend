from django.contrib import admin

from core.modules.organizations.models.organization import (
    Organization,
    OrganizationMember,
)


class OrganizationMemberInline(admin.TabularInline):
    model = OrganizationMember
    extra = 0


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    readonly_fields = (
        "id",)
    list_display = ("name", "owner", "is_personal", "is_active", "created_at")
    list_filter = ("is_personal", "is_active", "created_at")
    search_fields = ("name", "owner__email")
    inlines = [OrganizationMemberInline]


@admin.register(OrganizationMember)
class OrganizationMemberAdmin(admin.ModelAdmin):
    list_display = ("organization", "user", "role", "joined_at")
    list_filter = ("role",)
    search_fields = ("organization__name", "user__email")
