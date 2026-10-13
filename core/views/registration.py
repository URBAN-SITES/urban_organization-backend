from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.response_messages import (
    MSG_CODE_SENT,
    MSG_CODE_VALID,
    MSG_USER_CREATED,
)
from core.serializers.registration import (
    RegistrationConfirmSerializer,
    RegistrationRequestSerializer,
    RegistrationVerifySerializer,
)
from core.services.registration import RegistrationService
from core.spectacular_serializers import (
    CodeIsInvalidSerializer,
    CodeIsValidSerializer,
    EmailAlreadyExistsSerializer,
    RequestSentSerializer,
    ServiceUnavaibleSerializer,
    UserCreatedSerializer,
)


class RegistrationRequestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    @extend_schema(
        summary="Step 1: Request registration code",
        request=RegistrationRequestSerializer,
        responses={
            200: RequestSentSerializer,
            400: EmailAlreadyExistsSerializer,
            503: ServiceUnavaibleSerializer,
        },
    )
    def post(self, request):
        serializer = RegistrationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        RegistrationService.request_registration(
            email=serializer.validated_data["email"]
        )
        return Response({"detail": MSG_CODE_SENT}, status.HTTP_201_CREATED)


class RegistrationVerifyView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    @extend_schema(
        summary="Step 2: Verify registration code",
        request=RegistrationVerifySerializer,
        responses={
            200: CodeIsValidSerializer,
            400: CodeIsInvalidSerializer,
        },
    )
    def post(self, request):
        serializer = RegistrationVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        RegistrationService.verify_code(
            email=serializer.validated_data["email"],
            code=serializer.validated_data["code"],
        )
        return Response({"detail": MSG_CODE_VALID}, status.HTTP_200_OK)


class RegistrationConfirmView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    @extend_schema(
        summary="Step 3: Complete registration",
        request=RegistrationConfirmSerializer,
        responses={
            200: UserCreatedSerializer,
            400: CodeIsInvalidSerializer,
        },
    )
    def post(self, request):
        serializer = RegistrationConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        RegistrationService.confirm_registration(
            email=serializer.validated_data["email"],
            code=serializer.validated_data["code"],
            name=serializer.validated_data["name"],
            password=serializer.validated_data["password"],
        )
        return Response({"detail": MSG_USER_CREATED}, status.HTTP_200_OK)
