from django.urls import path

from core.modules.invitations.views.invite import (
    InviteAcceptView,
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
]
