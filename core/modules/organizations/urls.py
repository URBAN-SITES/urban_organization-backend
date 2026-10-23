from django.urls import path

from core.modules.organizations.views.organization import (
    OrganizationBySlugView,
    OrganizationDetailView,
    OrganizationListCreateView,
    OrganizationMemberDetailView,
    OrganizationMemberListCreateView,
)

app_name = "organizations"

urlpatterns = [
    path("by-slug/<slug:slug>/", OrganizationBySlugView.as_view(), name="by-slug"),
    path("", OrganizationListCreateView.as_view(), name="list"),
    path("<uuid:organization_id>/", OrganizationDetailView.as_view(), name="detail"),
    path(
        "<uuid:organization_id>/members/",
        OrganizationMemberListCreateView.as_view(),
        name="member-list",
    ),
    path(
        "<uuid:organization_id>/members/<int:member_id>/",
        OrganizationMemberDetailView.as_view(),
        name="member-detail",
    ),
]
