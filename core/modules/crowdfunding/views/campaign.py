from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.crowdfunding.serializers.campaign import (
    CampaignCreateSerializer,
    CampaignSerializer,
    CampaignUpdateSerializer,
    ContributionCreateSerializer,
    ContributionResponseSerializer,
    ContributionSerializer,
)
from core.modules.crowdfunding.services.campaign import CampaignService
from core.modules.payments.services.payment import PaymentService
from core.modules.payments.views.payment import PAYMENT_NOTIFICATION_URL


@extend_schema(tags=["Vaquinhas"])
class CampaignListCreateView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CampaignSerializer

    def get_queryset(self):
        return CampaignService.list_for(
            self.request.user, self.kwargs["organization_id"]
        )

    @extend_schema(summary="Campaigns of an organization")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Create a campaign (owner or admin)",
        request=CampaignCreateSerializer,
        responses={201: CampaignSerializer},
    )
    def post(self, request, organization_id):
        serializer = CampaignCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        campaign = CampaignService.create(
            request.user, organization_id, serializer.validated_data
        )
        return Response(CampaignSerializer(campaign).data, status.HTTP_201_CREATED)


@extend_schema(tags=["Vaquinhas"])
class CampaignDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Campaign with its raised total", responses=CampaignSerializer
    )
    def get(self, request, campaign_id):
        # refresh my own pending PIX payments so the total is not stale
        PaymentService.sync_pending_for_user(request.user)
        campaign = CampaignService.get(request.user, campaign_id)
        return Response(CampaignSerializer(campaign).data)

    @extend_schema(
        summary="Edit or close a campaign (owner or admin)",
        request=CampaignUpdateSerializer,
        responses=CampaignSerializer,
    )
    def patch(self, request, campaign_id):
        serializer = CampaignUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        campaign = CampaignService.update(
            request.user, campaign_id, serializer.validated_data
        )
        return Response(CampaignSerializer(campaign).data)


@extend_schema(tags=["Vaquinhas"])
class ContributionListCreateView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ContributionSerializer

    def get_queryset(self):
        return CampaignService.list_contributions(
            self.request.user, self.kwargs["campaign_id"]
        )

    @extend_schema(summary="Approved contributions (anonymous ones hide the name)")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Contribute with a Mercado Pago PIX",
        request=ContributionCreateSerializer,
        responses={201: ContributionResponseSerializer},
    )
    def post(self, request, campaign_id):
        serializer = ContributionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = CampaignService.contribute(
            request.user,
            campaign_id,
            notification_url=PAYMENT_NOTIFICATION_URL,
            message=serializer.validated_data.get("message", ""),
            **{
                key: serializer.validated_data[key]
                for key in ("amount", "cpf", "name", "anonymous")
            },
        )
        return Response(result, status.HTTP_201_CREATED)
