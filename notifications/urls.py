from django.urls import path

from notifications.views.notification import (
    DeviceTokenView,
    NotificationListView,
    NotificationReadAllView,
    NotificationReadView,
    SendPushView,
)

app_name = "notifications"

urlpatterns = [
    path("", NotificationListView.as_view(), name="list"),
    path("send/", SendPushView.as_view(), name="send"),
    path("devices/", DeviceTokenView.as_view(), name="device"),
    path("read-all/", NotificationReadAllView.as_view(), name="read-all"),
    path(
        "<int:notification_id>/read/",
        NotificationReadView.as_view(),
        name="read",
    ),
]
