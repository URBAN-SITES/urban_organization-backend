from django.urls import path

from core.modules.user_settings.views.user_settings import UserSettingsView

app_name = "user_settings"
urlpatterns = [path("", UserSettingsView.as_view(), name="me")]
