from django.contrib import admin

from core.modules.teams.models.team import SectorTeam, Team, TeamMember


class TeamMemberInline(admin.TabularInline):
    model = TeamMember
    extra = 0


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "is_active", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "organization__name")
    inlines = [TeamMemberInline]


@admin.register(SectorTeam)
class SectorTeamAdmin(admin.ModelAdmin):
    list_display = ("team", "sector", "role")
    list_filter = ("role",)
    search_fields = ("team__name", "sector__name")
