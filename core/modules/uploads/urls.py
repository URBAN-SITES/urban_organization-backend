from django.urls import path

from core.modules.uploads.views.upload import FileUploadView, StoredFileView

app_name = "uploads"

urlpatterns = [
    path("", FileUploadView.as_view(), name="file-upload"),
    path("files/<uuid:file_id>/", StoredFileView.as_view(), name="stored-file"),
]
