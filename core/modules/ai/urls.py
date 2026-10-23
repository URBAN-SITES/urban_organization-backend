from django.urls import path

from core.modules.ai.views.analysis import AIAnalysisView
from core.modules.ai.views.ask import AIAskView
from core.modules.ai.views.tester import analysis_tester

app_name = "ai"

urlpatterns = [
    path("test/", analysis_tester, name="test"),
    path("ask/", AIAskView.as_view(), name="ask"),
    path("analyze/", AIAnalysisView.as_view(), name="analyze"),
]
