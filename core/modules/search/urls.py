from django.urls import path

from core.modules.search.views.search import SearchView

app_name = "search"

urlpatterns = [
    path(
        "organizations/<uuid:organization_id>/search/",
        SearchView.as_view(),
        name="search",
    ),
]
