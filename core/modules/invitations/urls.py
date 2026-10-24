from django.urls import path

from core.modules.invitations.views.invite import (
    InviteAcceptView,
    MyInviteAcceptView,
    MyInviteDeclineView,
    MyInviteListView,
    OrganizationInviteDetailView,
    OrganizationInviteListCreateView,
)

app_name = "invitations"

# mounted at the API root: it has organization-scoped and user-scoped routes
urlpatterns = [
    path(
        "organizations/<uuid:organization_id>/invitations/",
        OrganizationInviteListCreateView.as_view(),
        name="organization-list",
    ),
    path(
        "organizations/<uuid:organization_id>/invitations/<uuid:invite_id>/",
        OrganizationInviteDetailView.as_view(),
        name="organization-detail",
    ),
    path("invitations/mine/", MyInviteListView.as_view(), name="mine"),
    path("invitations/accept/", InviteAcceptView.as_view(), name="accept"),
    path(
        "invitations/<uuid:invite_id>/accept/",
        MyInviteAcceptView.as_view(),
        name="mine-accept",
    ),
    path(
        "invitations/<uuid:invite_id>/decline/",
        MyInviteDeclineView.as_view(),
        name="mine-decline",
    ),
]
