from django.urls import path

from core.modules.calendar_sync.views.drive import (
    DriveAttachView,
    DriveFilesView,
    DriveUploadView,
)
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
    path("drive/files/", DriveFilesView.as_view(), name="drive-files"),
    path("drive/upload/", DriveUploadView.as_view(), name="drive-upload"),
    path("drive/attach/", DriveAttachView.as_view(), name="drive-attach"),
]
