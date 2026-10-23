from django.urls import path

from core.modules.calendar_sync.views.google import (
    GoogleAuthorizeView,
    GoogleConnectView,
    GoogleStatusView,
)

app_name = "calendar_sync"

urlpatterns = [
    path("", GoogleStatusView.as_view(), name="status"),
    path("authorize/", GoogleAuthorizeView.as_view(), name="authorize"),
    path("connect/", GoogleConnectView.as_view(), name="connect"),
]
