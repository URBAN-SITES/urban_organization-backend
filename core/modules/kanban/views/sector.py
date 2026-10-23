from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.kanban.serializers.sector import (
    SectorMemberAddSerializer,
    SectorMemberRoleSerializer,
    SectorMemberSerializer,
    SectorProgressSerializer,
    SectorSerializer,
    SectorTeamAddSerializer,
    SectorTeamSerializer,
    StatusSerializer,
)
from core.modules.kanban.services.sector import SectorService
from core.modules.kanban.services.status import StatusService


class SectorListCreateView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SectorSerializer

    @extend_schema(summary="List the sectors I can see in an organization")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return SectorService.list_for(self.request.user, self.kwargs["organization_id"])

    @extend_schema(
        summary="Create a sector (organization member+); you become its manager",
        request=SectorSerializer,
        responses={201: SectorSerializer},
    )
    def post(self, request, organization_id):
        serializer = SectorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sector = SectorService.create(
            request.user, organization_id, **serializer.validated_data
        )
        return Response(SectorSerializer(sector).data, status=status.HTTP_201_CREATED)


class SectorDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get a sector (adds my_role)", responses={200: SectorSerializer}
    )
    def get(self, request, sector_id):
        sector, role = SectorService.get_sector(request.user, sector_id)
        return Response({**SectorSerializer(sector).data, "my_role": role})

    @extend_schema(
        summary="Update a sector (manager)",
        request=SectorSerializer,
        responses={200: SectorSerializer},
    )
    def patch(self, request, sector_id):
        serializer = SectorSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        sector = SectorService.update(
            request.user, sector_id, serializer.validated_data
        )
        return Response(SectorSerializer(sector).data)

    @extend_schema(summary="Delete a sector (manager)", responses={204: None})
    def delete(self, request, sector_id):
        SectorService.delete(request.user, sector_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SectorProgressView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Progress: total, completed, overdue and percent",
        responses={200: SectorProgressSerializer},
    )
    def get(self, request, sector_id):
        return Response(SectorService.progress(request.user, sector_id))


class SectorMemberListCreateView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SectorMemberSerializer

    @extend_schema(summary="List the participants of a sector")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return SectorService.list_members(self.request.user, self.kwargs["sector_id"])

    @extend_schema(
        summary="Add an organization member to the sector (manager)",
        request=SectorMemberAddSerializer,
        responses={201: SectorMemberSerializer},
    )
    def post(self, request, sector_id):
        serializer = SectorMemberAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = SectorService.add_member(
            request.user, sector_id, **serializer.validated_data
        )
        return Response(
            SectorMemberSerializer(member).data, status=status.HTTP_201_CREATED
        )


class SectorMemberDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Change a participant's role (manager)",
        request=SectorMemberRoleSerializer,
        responses={200: SectorMemberSerializer},
    )
    def patch(self, request, sector_id, member_id):
        serializer = SectorMemberRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = SectorService.change_member_role(
            request.user, sector_id, member_id, serializer.validated_data["role"]
        )
        return Response(SectorMemberSerializer(member).data)

    @extend_schema(
        summary="Remove a participant, or leave the sector", responses={204: None}
    )
    def delete(self, request, sector_id, member_id):
        SectorService.remove_member(request.user, sector_id, member_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SectorTeamListCreateView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SectorTeamSerializer

    @extend_schema(summary="List the teams linked to a sector")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return SectorService.list_teams(self.request.user, self.kwargs["sector_id"])

    @extend_schema(
        summary="Give a whole team access to the sector (manager)",
        request=SectorTeamAddSerializer,
        responses={201: SectorTeamSerializer},
    )
    def post(self, request, sector_id):
        serializer = SectorTeamAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        link = SectorService.add_team(
            request.user, sector_id, **serializer.validated_data
        )
        return Response(SectorTeamSerializer(link).data, status=status.HTTP_201_CREATED)


class SectorTeamDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Unlink a team from the sector (manager)", responses={204: None}
    )
    def delete(self, request, sector_id, link_id):
        SectorService.remove_team(request.user, sector_id, link_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class StatusListCreateView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = StatusSerializer

    @extend_schema(summary="List the board columns of a sector")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return StatusService.list_for(self.request.user, self.kwargs["sector_id"])

    @extend_schema(
        summary="Add a column (manager)",
        request=StatusSerializer,
        responses={201: StatusSerializer},
    )
    def post(self, request, sector_id):
        serializer = StatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created = StatusService.create(
            request.user, sector_id, **serializer.validated_data
        )
        return Response(StatusSerializer(created).data, status=status.HTTP_201_CREATED)


class StatusDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Update a column (manager)",
        request=StatusSerializer,
        responses={200: StatusSerializer},
    )
    def patch(self, request, sector_id, status_id):
        serializer = StatusSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = StatusService.update(
            request.user, sector_id, status_id, serializer.validated_data
        )
        return Response(StatusSerializer(updated).data)

    @extend_schema(summary="Delete an empty column (manager)", responses={204: None})
    def delete(self, request, sector_id, status_id):
        StatusService.delete(request.user, sector_id, status_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
