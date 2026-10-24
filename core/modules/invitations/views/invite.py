from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.invitations.serializers.invite import (
    InviteAcceptedSerializer,
    InviteAcceptSerializer,
    InviteCreateSerializer,
    InviteSerializer,
)
from core.modules.invitations.services.invite import InviteService


@extend_schema(tags=["Ingressar Em Uma Organização"])
class OrganizationInviteListCreateView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InviteSerializer

    @extend_schema(summary="List the invitations of an organization (admin or owner)")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return InviteService.list_for_organization(
            self.request.user, self.kwargs["organization_id"]
        )

    @extend_schema(
        summary="Invite an e-mail to the organization (admin or owner)",
        request=InviteCreateSerializer,
        responses={201: InviteSerializer},
    )
    def post(self, request, organization_id):
        serializer = InviteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invite = InviteService.create(
            request.user, organization_id, **serializer.validated_data
        )
        return Response(InviteSerializer(invite).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Ingressar Em Uma Organização"])
class OrganizationInviteDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Revoke a pending invitation (admin or owner)", responses={204: None}
    )
    def delete(self, request, organization_id, invite_id):
        InviteService.revoke(request.user, organization_id, invite_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Ingressar Em Uma Organização"])
class MyInviteListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InviteSerializer

    @extend_schema(summary="List pending invitations addressed to me")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return InviteService.list_mine(self.request.user)


@extend_schema(tags=["Ingressar Em Uma Organização"])
class InviteAcceptView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Accept an invitation with the token from the e-mail",
        request=InviteAcceptSerializer,
        responses={200: InviteAcceptedSerializer},
    )
    def post(self, request):
        serializer = InviteAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = InviteService.accept(request.user, serializer.validated_data["token"])
        return Response(InviteAcceptedSerializer(member).data)


@extend_schema(tags=["Ingressar Em Uma Organização"])
class MyInviteAcceptView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Accept one of my pending invitations",
        responses={200: InviteAcceptedSerializer},
    )
    def post(self, request, invite_id):
        member = InviteService.accept_by_id(request.user, invite_id)
        return Response(InviteAcceptedSerializer(member).data)


@extend_schema(tags=["Ingressar Em Uma Organização"])
class MyInviteDeclineView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Decline one of my pending invitations", responses={204: None}
    )
    def post(self, request, invite_id):
        InviteService.decline(request.user, invite_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
