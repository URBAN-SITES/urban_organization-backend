from django.urls import path

from core.modules.crowdfunding.views.campaign import (
    CampaignDetailView,
    CampaignListCreateView,
    ContributionListCreateView,
    ContributionStatusView,
    TaskCampaignListCreateView,
)

app_name = "crowdfunding"

# mounted at the API root: organization-scoped and campaign-scoped routes
urlpatterns = [
    path(
        "organizations/<uuid:organization_id>/campaigns/",
        CampaignListCreateView.as_view(),
        name="campaign-list",
    ),
    path(
        "tasks/<uuid:task_id>/campaigns/",
        TaskCampaignListCreateView.as_view(),
        name="task-campaign-list",
    ),
    path(
        "contributions/<uuid:contribution_id>/",
        ContributionStatusView.as_view(),
        name="contribution-status",
    ),
    path(
        "campaigns/<uuid:campaign_id>/",
        CampaignDetailView.as_view(),
        name="campaign-detail",
    ),
    path(
        "campaigns/<uuid:campaign_id>/contributions/",
        ContributionListCreateView.as_view(),
        name="contribution-list",
    ),
]
