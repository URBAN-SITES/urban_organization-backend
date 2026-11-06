from django.urls import path

from core.modules.calls.views.calls import (
    CallDeclineView,
    CallDetailView,
    CallJoinView,
    CallLeaveView,
    CallListCreateView,
    CallMediaView,
    CallSignalView,
    IceServersView,
)

app_name = "calls"

urlpatterns = [
    path("", CallListCreateView.as_view(), name="list"),
    path("ice-servers/", IceServersView.as_view(), name="ice-servers"),
    path("<uuid:call_id>/", CallDetailView.as_view(), name="detail"),
    path("<uuid:call_id>/join/", CallJoinView.as_view(), name="join"),
    path("<uuid:call_id>/decline/", CallDeclineView.as_view(), name="decline"),
    path("<uuid:call_id>/leave/", CallLeaveView.as_view(), name="leave"),
    path("<uuid:call_id>/signal/", CallSignalView.as_view(), name="signal"),
    path("<uuid:call_id>/media/", CallMediaView.as_view(), name="media"),
]
