from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.search.serializers.search import SearchResultSerializer
from core.modules.search.services.search import SearchService


@extend_schema(tags=["Busca"])
class SearchView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Search tasks, people and files of an organization",
        parameters=[
            OpenApiParameter("q", str, required=True, description="2+ characters")
        ],
        responses={200: SearchResultSerializer},
    )
    def get(self, request, organization_id):
        results = SearchService.search(
            request.user, organization_id, request.query_params.get("q", "")
        )
        return Response(SearchResultSerializer(results).data)
