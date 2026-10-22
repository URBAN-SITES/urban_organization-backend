from django.urls import path

from uploads.views.upload import FileUploadView

app_name = "uploads"

urlpatterns = [
    path("", FileUploadView.as_view(), name="file-upload"),
]
