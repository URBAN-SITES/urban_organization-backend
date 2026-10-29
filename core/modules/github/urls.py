from django.urls import path

from core.modules.github.views.github import (
    GitHubAuthorizeView,
    GitHubCallbackView,
    GitHubConnectionView,
    GitHubIdentityView,
    GitHubRepositoriesView,
    GitHubStatusView,
    GitHubWebhookView,
    ProjectRepositoriesView,
    ProjectRepositoryDetailView,
    RepositoryActivityView,
    TaskGitHubLinkDetailView,
    TaskGitHubLinksView,
    TaskGitHubSearchView,
)

app_name = "github"

urlpatterns = [
    path("integrations/github/", GitHubStatusView.as_view(), name="status"),
    path(
        "integrations/github/authorize/",
        GitHubAuthorizeView.as_view(),
        name="authorize",
    ),
    path(
        "integrations/github/callback/", GitHubCallbackView.as_view(), name="callback"
    ),
    path(
        "integrations/github/connection/",
        GitHubConnectionView.as_view(),
        name="connection",
    ),
    path(
        "integrations/github/identity/", GitHubIdentityView.as_view(), name="identity"
    ),
    path(
        "integrations/github/repositories/",
        GitHubRepositoriesView.as_view(),
        name="repositories",
    ),
    path("integrations/github/webhook/", GitHubWebhookView.as_view(), name="webhook"),
    path(
        "sectors/<uuid:sector_id>/repositories/",
        ProjectRepositoriesView.as_view(),
        name="project-repositories",
    ),
    path(
        "sectors/<uuid:sector_id>/repositories/<uuid:repository_id>/",
        ProjectRepositoryDetailView.as_view(),
        name="project-repository",
    ),
    path(
        "github/repositories/<uuid:repository_id>/activity/",
        RepositoryActivityView.as_view(),
        name="repository-activity",
    ),
    path(
        "tasks/<uuid:task_id>/github/", TaskGitHubLinksView.as_view(), name="task-links"
    ),
    path(
        "tasks/<uuid:task_id>/github/search/",
        TaskGitHubSearchView.as_view(),
        name="task-search",
    ),
    path(
        "tasks/<uuid:task_id>/github/<uuid:link_id>/",
        TaskGitHubLinkDetailView.as_view(),
        name="task-link",
    ),
]
