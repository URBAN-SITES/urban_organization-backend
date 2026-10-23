from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.organizations.serializers.organization import (
    OrganizationMemberAddSerializer,
    OrganizationMemberRoleSerializer,
    OrganizationMemberSerializer,
    OrganizationSerializer,
)
from core.modules.organizations.services.organization import OrganizationService


@extend_schema(tags=["Organizações"])
class OrganizationListCreateView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OrganizationSerializer

    @extend_schema(summary="List my organizations (creates the personal one)")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return OrganizationService.list_for(self.request.user)

    @extend_schema(
        summary="Create an organization (you become its owner)",
        request=OrganizationSerializer,
        responses={201: OrganizationSerializer},
    )
    def post(self, request):
        serializer = OrganizationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = OrganizationService.create(
            request.user, **serializer.validated_data
        )
        return Response(
            OrganizationSerializer(organization).data, status=status.HTTP_201_CREATED
        )


@extend_schema(tags=["Organizações"])
class OrganizationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get an organization", responses={200: OrganizationSerializer}
    )
    def get(self, request, organization_id):
        membership = OrganizationService.get_membership(request.user, organization_id)
        return Response(OrganizationSerializer(membership.organization).data)

    @extend_schema(
        summary="Update an organization (admin or owner)",
        request=OrganizationSerializer,
        responses={200: OrganizationSerializer},
    )
    def patch(self, request, organization_id):
        serializer = OrganizationSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        organization = OrganizationService.update(
            request.user, organization_id, serializer.validated_data
        )
        return Response(OrganizationSerializer(organization).data)

    @extend_schema(
        summary="Delete an organization (owner, not the personal one)",
        responses={204: None},
    )
    def delete(self, request, organization_id):
        OrganizationService.delete(request.user, organization_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Organizações"])
class OrganizationMemberListCreateView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OrganizationMemberSerializer

    @extend_schema(summary="List the members of an organization")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return OrganizationService.list_members(
            self.request.user, self.kwargs["organization_id"]
        )

    @extend_schema(
        summary="Add an existing user by e-mail (admin or owner)",
        request=OrganizationMemberAddSerializer,
        responses={201: OrganizationMemberSerializer},
    )
    def post(self, request, organization_id):
        serializer = OrganizationMemberAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = OrganizationService.add_member(
            request.user, organization_id, **serializer.validated_data
        )
        return Response(
            OrganizationMemberSerializer(member).data, status=status.HTTP_201_CREATED
        )


@extend_schema(tags=["Organizações"])
class OrganizationMemberDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Change a member's role (admin or owner)",
        request=OrganizationMemberRoleSerializer,
        responses={200: OrganizationMemberSerializer},
    )
    def patch(self, request, organization_id, member_id):
        serializer = OrganizationMemberRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = OrganizationService.change_role(
            request.user, organization_id, member_id, serializer.validated_data["role"]
        )
        return Response(OrganizationMemberSerializer(member).data)

    @extend_schema(
        summary="Remove a member, or leave the organization",
        responses={204: None},
    )
    def delete(self, request, organization_id, member_id):
        OrganizationService.remove_member(request.user, organization_id, member_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
