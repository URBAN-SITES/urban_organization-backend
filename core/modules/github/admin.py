from django.contrib import admin

from core.modules.github.models.github import (
    GitHubConnection,
    GitHubIdentity,
    ProjectRepository,
)


@admin.register(GitHubConnection)
class GitHubConnectionAdmin(admin.ModelAdmin):
    list_display = ("user", "login", "expires_at", "created_at")
    search_fields = ("user__email", "login")
    exclude = ("access_token", "refresh_token")  # never show credentials


@admin.register(GitHubIdentity)
class GitHubIdentityAdmin(admin.ModelAdmin):
    list_display = ("user", "login", "github_id")
    search_fields = ("user__email", "login")


@admin.register(ProjectRepository)
class ProjectRepositoryAdmin(admin.ModelAdmin):
    list_display = ("full_name", "sector", "private", "created_at")
    search_fields = ("full_name",)
