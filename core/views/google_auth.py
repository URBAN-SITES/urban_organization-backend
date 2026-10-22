from django.middleware import csrf
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.response_messages import MSG_LOGIN_SUCCESSFUL
from core.serializers.google_auth import GoogleLoginSerializer
from core.services.google_auth import GoogleAuthService
from core.spectacular_serializers import (
    IncorrectAuthenticationsCredentialsSerializer,
    LoginSucessfulSerializer,
)
from core.utils.cookies import set_auth_cookies


class GoogleLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Log in or sign up with Google",
        description="Send the Google ID token (`credential`) from Google Identity Services. Creates the account on first login and sets the same JWT cookies as the e-mail login.",
        request=GoogleLoginSerializer,
        responses={
            200: LoginSucessfulSerializer,
            401: IncorrectAuthenticationsCredentialsSerializer,
        },
    )
    def post(self, request):
        serializer = GoogleLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tokens = GoogleAuthService.login(
            credential=serializer.validated_data["credential"],
            user_agent_string=request.META.get("HTTP_USER_AGENT", ""),
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        response = Response({"detail": MSG_LOGIN_SUCCESSFUL}, status.HTTP_200_OK)
        set_auth_cookies(response, tokens)
        csrf.get_token(request)
        return response
