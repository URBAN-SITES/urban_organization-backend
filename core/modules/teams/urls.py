from django.urls import path

from core.modules.teams.views.team import (
    TeamDetailView,
    TeamListCreateView,
    TeamMemberDetailView,
    TeamMemberListCreateView,
)

app_name = "teams"

# mounted under organizations/<uuid:organization_id>/teams/
urlpatterns = [
    path("", TeamListCreateView.as_view(), name="list"),
    path("<uuid:team_id>/", TeamDetailView.as_view(), name="detail"),
    path(
        "<uuid:team_id>/members/",
        TeamMemberListCreateView.as_view(),
        name="member-list",
    ),
    path(
        "<uuid:team_id>/members/<int:member_id>/",
        TeamMemberDetailView.as_view(),
        name="member-detail",
    ),
]
