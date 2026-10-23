from django.contrib import admin

from core.modules.invitations.models.invite import OrganizationInvite


@admin.register(OrganizationInvite)
class OrganizationInviteAdmin(admin.ModelAdmin):
    list_display = ("email", "organization", "role", "status", "expires_at")
    list_filter = ("status", "role", "created_at")
    search_fields = ("email", "organization__name")
    readonly_fields = ("token_hash",)
