from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.teams.serializers.team import (
    TeamMemberAddSerializer,
    TeamMemberRoleSerializer,
    TeamMemberSerializer,
    TeamSerializer,
)
from core.modules.teams.services.team import TeamService


@extend_schema(tags=["Times"])
class TeamListCreateView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TeamSerializer

    @extend_schema(summary="List the teams of an organization")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return TeamService.list_for(self.request.user, self.kwargs["organization_id"])

    @extend_schema(
        summary="Create a team (organization admin or owner; you become its lead)",
        request=TeamSerializer,
        responses={201: TeamSerializer},
    )
    def post(self, request, organization_id):
        serializer = TeamSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        team = TeamService.create(
            request.user, organization_id, **serializer.validated_data
        )
        return Response(TeamSerializer(team).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Times"])
class TeamDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Get a team", responses={200: TeamSerializer})
    def get(self, request, organization_id, team_id):
        team = TeamService.get(request.user, organization_id, team_id)
        return Response(TeamSerializer(team).data)

    @extend_schema(
        summary="Update a team (org admin/owner or team lead)",
        request=TeamSerializer,
        responses={200: TeamSerializer},
    )
    def patch(self, request, organization_id, team_id):
        serializer = TeamSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        team = TeamService.update(
            request.user, organization_id, team_id, serializer.validated_data
        )
        return Response(TeamSerializer(team).data)

    @extend_schema(
        summary="Delete a team (organization admin or owner)", responses={204: None}
    )
    def delete(self, request, organization_id, team_id):
        TeamService.delete(request.user, organization_id, team_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Times"])
class TeamMemberListCreateView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TeamMemberSerializer

    @extend_schema(summary="List the members of a team")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return TeamService.list_members(
            self.request.user, self.kwargs["organization_id"], self.kwargs["team_id"]
        )

    @extend_schema(
        summary="Add an organization member to the team (org admin/owner or lead)",
        request=TeamMemberAddSerializer,
        responses={201: TeamMemberSerializer},
    )
    def post(self, request, organization_id, team_id):
        serializer = TeamMemberAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = TeamService.add_member(
            request.user, organization_id, team_id, **serializer.validated_data
        )
        return Response(
            TeamMemberSerializer(member).data, status=status.HTTP_201_CREATED
        )


@extend_schema(tags=["Times"])
class TeamMemberDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Change a team member's role (org admin/owner or lead)",
        request=TeamMemberRoleSerializer,
        responses={200: TeamMemberSerializer},
    )
    def patch(self, request, organization_id, team_id, member_id):
        serializer = TeamMemberRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = TeamService.change_role(
            request.user,
            organization_id,
            team_id,
            member_id,
            serializer.validated_data["role"],
        )
        return Response(TeamMemberSerializer(member).data)

    @extend_schema(
        summary="Remove a team member, or leave the team", responses={204: None}
    )
    def delete(self, request, organization_id, team_id, member_id):
        TeamService.remove_member(request.user, organization_id, team_id, member_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
