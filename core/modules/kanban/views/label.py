from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models.user import User
from core.modules.kanban.serializers.task import LabelSerializer, PersonSerializer
from core.modules.kanban.services.label import LabelService
from core.modules.kanban.services.sector import SectorService


@extend_schema(tags=["Tarefas"])
class LabelListCreateView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LabelSerializer

    @extend_schema(summary="List a sector's labels")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return LabelService.list_for(self.request.user, self.kwargs["sector_id"])

    @extend_schema(
        summary="Create a label (editor+)",
        request=LabelSerializer,
        responses={201: LabelSerializer},
    )
    def post(self, request, sector_id):
        serializer = LabelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        label = LabelService.create(
            request.user, sector_id, **serializer.validated_data
        )
        return Response(LabelSerializer(label).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Tarefas"])
class LabelDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Rename or recolor a label (editor+)",
        request=LabelSerializer,
        responses={200: LabelSerializer},
    )
    def patch(self, request, label_id):
        serializer = LabelSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        label = LabelService.update(request.user, label_id, serializer.validated_data)
        return Response(LabelSerializer(label).data)

    @extend_schema(
        summary="Delete a label; it leaves every task (editor+)", responses={204: None}
    )
    def delete(self, request, label_id):
        LabelService.delete(request.user, label_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Setores"])
class SectorPeopleView(ListAPIView):
    """Everyone who can see the sector: options for assignee and @mentions."""

    permission_classes = [IsAuthenticated]
    serializer_class = PersonSerializer

    @extend_schema(summary="People with access to a sector")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        sector, _role = SectorService.get_sector(
            self.request.user, self.kwargs["sector_id"]
        )
        ids = SectorService.participant_ids(sector)
        return User.objects.filter(id__in=ids, is_active=True).order_by("name", "id")
