from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.response_messages import MSG_CODE_SENT, MSG_CODE_VALID, MSG_PASWORD_RESET
from core.serializers.password_reset import (
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PasswordResetVerifySerializer,
)
from core.services.password_reset import PasswordResetService
from core.spectacular_serializers import (
    CodeIsInvalidSerializer,
    CodeIsValidSerializer,
    PasswordResetSerializer,
    RequestSentSerializer,
    ServiceUnavaibleSerializer,
)


class PasswordResetRequestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    @extend_schema(
        summary="Step 1: Request password reset code",
        request=PasswordResetRequestSerializer,
        responses={
            200: RequestSentSerializer,
            503: ServiceUnavaibleSerializer,
        },
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        PasswordResetService.request_reset(serializer.validated_data["email"])

        return Response(
            {"detail": MSG_CODE_SENT},
            status.HTTP_200_OK,
        )


class PasswordResetVerifyView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    @extend_schema(
        summary="Step 2: Verify password reset code",
        request=PasswordResetVerifySerializer,
        responses={
            200: CodeIsValidSerializer,
            400: CodeIsInvalidSerializer,
        },
    )
    def post(self, request):
        serializer = PasswordResetVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        PasswordResetService.verify_code(
            email=serializer.validated_data["email"],
            code=serializer.validated_data["code"],
        )

        return Response({"detail": MSG_CODE_VALID}, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    @extend_schema(
        summary="Step 3: Confirm password reset",
        request=PasswordResetConfirmSerializer,
        responses={
            200: PasswordResetSerializer,
            400: CodeIsInvalidSerializer,
        },
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        PasswordResetService.confirm_reset(
            email=serializer.validated_data["email"],
            code=serializer.validated_data["code"],
            new_password=serializer.validated_data["new_password"],
        )

        return Response({"detail": MSG_PASWORD_RESET}, status.HTTP_200_OK)
