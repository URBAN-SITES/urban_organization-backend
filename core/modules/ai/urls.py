from django.urls import path

from core.modules.ai.views.ask import AIAskView

app_name = "ai"

urlpatterns = [
    path("ask/", AIAskView.as_view(), name="ask"),
]
