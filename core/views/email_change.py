from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.response_messages import MSG_CODE_SENT, MSG_CODE_VALID, MSG_EMAIL_CHANGED
from core.serializers.email_change import (
    EmailChangeConfirmSerializer,
    EmailChangeRequestSerializer,
    EmailChangeVerifySerializer,
)
from core.services.email_change import EmailChangeService
from core.spectacular_serializers import (
    CodeIsInvalidSerializer,
    CodeIsValidSerializer,
    NewEmailAlreadyExistsSerializer,
    NewEmailChangedSerializer,
    NotAuthenticatedSerializer,
    RequestSentSerializer,
    ServiceUnavaibleSerializer,
)


@extend_schema(tags=["Perfil"])
class EmailChangeRequestView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "auth"

    @extend_schema(
        summary="Step 1: Request e-mail change",
        request=EmailChangeRequestSerializer,
        responses={
            200: RequestSentSerializer,
            400: NewEmailAlreadyExistsSerializer,
            401: NotAuthenticatedSerializer,
            503: ServiceUnavaibleSerializer,
        },
    )
    def post(self, request):
        serializer = EmailChangeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        EmailChangeService.request_change(
            user=request.user, new_email=serializer.validated_data["new_email"]
        )
        return Response({"detail": MSG_CODE_SENT}, status=status.HTTP_200_OK)


@extend_schema(tags=["Perfil"])
class EmailChangeVerifyView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "auth"

    @extend_schema(
        summary="Step 2: Verify e-mail change code",
        request=EmailChangeVerifySerializer,
        responses={
            200: CodeIsValidSerializer,
            400: CodeIsInvalidSerializer,
        },
    )
    def post(self, request):
        serializer = EmailChangeVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        EmailChangeService.verify_code(
            user=request.user, code=serializer.validated_data["code"]
        )
        return Response({"detail": MSG_CODE_VALID}, status=status.HTTP_200_OK)


@extend_schema(tags=["Perfil"])
class EmailChangeConfirmView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "auth"

    @extend_schema(
        summary="Step 3: Confirm e-mail change",
        request=EmailChangeConfirmSerializer,
        responses={
            200: NewEmailChangedSerializer,
            400: CodeIsInvalidSerializer,
        },
    )
    def post(self, request):
        serializer = EmailChangeConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        EmailChangeService.confirm_change(
            user=request.user,
            code=serializer.validated_data["code"],
            current_password=serializer.validated_data["password"],
        )
        return Response({"detail": MSG_EMAIL_CHANGED}, status=status.HTTP_200_OK)
