# import uuid

from django.middleware import csrf
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, NotFound
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.validators import ValidationError
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from core.models.user import User, UserSession
from core.response_messages import (
    MSG_CANNOT_DEACTIVATE_CURRENT_SESSION,
    MSG_INVALID_OR_EXPIRED_REFRESH_TOKEN,
    MSG_LOGIN_SUCCESSFUL,
    MSG_LOGOUT_SUCCESSFUL,
    MSG_NO_REFRESH_TOKEN_PROVIDED,
    MSG_REFRESH_TOKENS_SUCCESSFUL,
    MSG_SESSION_REVOKED_OR_INACTIVE,
    MSG_USER_DEACTIVATED,
    MSG_USER_NOT_FOUND,
    MSG_USER_REVOKED_ALL_SESSIONS,
    MSG_USER_SESSION_DEACTIVATED,
    MSG_USER_SESSION_NOT_FOUND,
)
from core.serializers.user import (
    LoginSerializer,
    UserListRetrieveSerializer,
    UserMeSerializer,
    UserSessionSerializer,
    UserUpdateSelfSerializer,
)
from core.services.user import AuthService, SessionService, UserService
from core.spectacular_serializers import (
    CannotDeactivateCurrentSessionSerializer,
    IncorrectAuthenticationsCredentialsSerializer,
    InvalidOrExpiredRefreshTokenSerializer,
    LoginSucessfulSerializer,
    LogoutSuccessfulSerializer,
    NotAuthenticatedSerializer,
    RefreshTokensSuccessfulSerializer,
    UserDeactivatedSerializer,
    UserNotFoundSerializer,
    UserRevokedAllSessionsSerializer,
    UserSessionDeactivatedSerializer,
    UserSessionNotFoundSerializer,
)
from core.utils.cookies import (
    get_auth_cookie_kwargs,
    get_auth_cookie_name,
    set_auth_cookies,
)

# TODO: add description and summary to all of views

# TODO: adicionar responses aos novos endpoints de resfresh e arrumar MSG_... deles nos erros (estão em português e sem gettext_lazy)


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


@extend_schema(tags=["Conta e Sessões"])
class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    @extend_schema(
        summary="Authenticate user and set JWT tokens in the browser cookies",
        description="When a user makes a request, the default authentication class defined in the DRF settings is not applied; that is, anyone can perform the operation. When the login is successful, JWT cookies are set in the browser. Considering different cases:\n\nA - User is not yet logged in (no cookies in the browser):\nThe operation proceeds, verifying the credentials (responses below) and setting the cookies.\n\nB - The user is already logged in (already has cookies in the browser):\nThe operation also proceeds normally too, however, the access and refresh cookies set in the previous login are invalidated within the blacklist.",
        request=LoginSerializer,
        responses={
            200: LoginSucessfulSerializer,
            401: IncorrectAuthenticationsCredentialsSerializer,
        },
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token_data = AuthService.login_user(
            email=serializer.validated_data.get("email"),
            password=serializer.validated_data.get("password"),
            user_agent_string=request.META.get("HTTP_USER_AGENT", ""),
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        response = Response(
            {"detail": MSG_LOGIN_SUCCESSFUL, "data": token_data}, status.HTTP_200_OK
        )
        set_auth_cookies(response, token_data)
        csrf.get_token(request)

        return response


@extend_schema(tags=["Conta e Sessões"])
class CustomTokenRefreshView(TokenRefreshView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Refresh the user session using refresh token setted in the user browser",
        request=LoginSerializer,
        responses={
            200: RefreshTokensSuccessfulSerializer,
            401: InvalidOrExpiredRefreshTokenSerializer,
        },
    )
    def post(self, request, *args, **kwargs):
        refresh_token_str = request.COOKIES.get("refresh_token")
        if not refresh_token_str:
            raise AuthenticationFailed(MSG_NO_REFRESH_TOKEN_PROVIDED)
        try:
            old_refresh_token = RefreshToken(refresh_token_str)
            old_jti = str(old_refresh_token.get("jti", ""))
        except TokenError:
            raise InvalidToken(MSG_INVALID_OR_EXPIRED_REFRESH_TOKEN)
        session_is_active = UserSession.objects.filter(
            refresh_jti=old_jti,
            is_active=True,
        ).exists()

        if not session_is_active:
            raise AuthenticationFailed(MSG_SESSION_REVOKED_OR_INACTIVE)
        data = (
            request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        )
        data["refresh"] = refresh_token_str
        serializer = self.get_serializer(data=data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            raise InvalidToken(e.args[0])

        response_data = serializer.validated_data
        new_access_token = response_data.get("access")
        new_refresh_token = response_data.get("refresh")
        if new_access_token and new_refresh_token:
            new_access_jti = str(AccessToken(new_access_token).get("jti", ""))
            new_refresh_jti = str(RefreshToken(new_refresh_token).get("jti", ""))
            SessionService.update_session_jtis(
                old_refresh_jti=old_jti,
                new_access_jti=new_access_jti,
                new_refresh_jti=new_refresh_jti,
            )
        response = Response(
            {"detail": MSG_REFRESH_TOKENS_SUCCESSFUL}, status.HTTP_200_OK
        )
        if new_access_token:
            response.set_cookie(
                get_auth_cookie_name(),
                new_access_token,
                **get_auth_cookie_kwargs(is_refresh=False),
            )
        if new_refresh_token:
            response.set_cookie(
                "refresh_token",
                new_refresh_token,
                **get_auth_cookie_kwargs(is_refresh=True),
            )

        return response


@extend_schema(tags=["Conta e Sessões"])
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Log out the user current session",
        description="Its purpose is to log the user out of their current session. It adds the refresh and access tokens defined in the user's browser to the blacklist table. It also instructs the browser to delete the cookies related to authentication.",
        request=None,
        responses={
            200: LogoutSuccessfulSerializer,
            401: NotAuthenticatedSerializer,
        },
    )
    def post(self, request):
        raw_access_token = request.COOKIES.get(get_auth_cookie_name())
        if raw_access_token:
            try:
                jti = str(AccessToken(raw_access_token).get("jti", ""))
                SessionService.deactivate_session_by_access_jti(request.user, jti)
            except TokenError:
                pass
        response = Response({"detail": MSG_LOGOUT_SUCCESSFUL}, status.HTTP_200_OK)
        cookie_kwargs = get_auth_cookie_kwargs()
        delete_kwargs = {
            "path": cookie_kwargs.get("path", "/"),
            "domain": cookie_kwargs.get("domain", None),
            "samesite": cookie_kwargs.get("samesite", "Lax"),
        }
        response.delete_cookie(get_auth_cookie_name(), **delete_kwargs)
        response.delete_cookie("refresh_token", **delete_kwargs)
        return response


@extend_schema(tags=["Conta e Sessões"])
class UserSessionsDeactivateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Deactivate a session",
        description="",
        request=None,
        responses={
            200: UserSessionDeactivatedSerializer,
            400: CannotDeactivateCurrentSessionSerializer,
            401: NotAuthenticatedSerializer,
            404: UserSessionNotFoundSerializer,
        },
        parameters=[
            OpenApiParameter(
                name="session_id",
                type=int,
                # TODO: when the model change int to uuid, change type here too
                location=OpenApiParameter.PATH,
                required=True,
            )
        ],
    )
    def delete(self, request, session_id):
        raw_access_token = request.COOKIES.get(get_auth_cookie_name())
        current_session = None
        if raw_access_token:
            try:
                current_jti = str(AccessToken(raw_access_token).get("jti", ""))
                current_session = UserSession.objects.filter(
                    access_jti=current_jti, user=request.user
                ).first()
            except TokenError:
                pass
        if current_session and current_session.id == session_id:
            raise ValidationError({"detail": MSG_CANNOT_DEACTIVATE_CURRENT_SESSION})
        try:
            SessionService.deactivate_session(request.user, session_id)
            return Response(
                {"detail": MSG_USER_SESSION_DEACTIVATED}, status.HTTP_200_OK
            )
        except UserSession.DoesNotExist:
            raise NotFound(MSG_USER_SESSION_NOT_FOUND)


@extend_schema(tags=["Conta e Sessões"])
class UserSessionsGetView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="List active user sessions",
        description="Returns all active sessions of the requesting user. And, indicates which session is the current.",
        request=None,
        responses={
            200: UserSessionSerializer(many=True),
            401: NotAuthenticatedSerializer,
        },
    )
    def get(self, request):
        raw_access_token = request.COOKIES.get(get_auth_cookie_name())
        sessions = SessionService.get_active_sessions_with_current(
            request.user, raw_access_token
        )
        serializer = UserSessionSerializer(sessions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(tags=["Conta e Sessões"])
class RevokeAllSessionsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Revoke all active sessions",
        description="Instantly revokes all active sessions for the requesting user across all devices by blacklisting all outstanding refresh tokens and setting all session records to inactive.",
        request=None,
        responses={
            200: UserRevokedAllSessionsSerializer,
            401: NotAuthenticatedSerializer,
        },
    )
    def post(self, request):
        SessionService.revoke_all_sessions(request.user)
        return Response({"detail": MSG_USER_REVOKED_ALL_SESSIONS}, status.HTTP_200_OK)


@extend_schema(tags=["Perfil"])
class UserMeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get current user profile",
        description="Retrieves the profile information for the currently authenticated user.",
        responses={
            200: UserMeSerializer,
            401: NotAuthenticatedSerializer,
        },
    )
    def get(self, request):
        serializer = UserMeSerializer(request.user)
        return Response(serializer.data, status.HTTP_200_OK)


@extend_schema(tags=["Perfil"])
class UserListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserListRetrieveSerializer
    filterset_fields = ["is_active"]
    search_fields = ["name", "email"]
    ordering_fields = ["name", "email", "created_at"]

    @extend_schema(
        summary="List users",
        description="Paginated list of users (`?page=`), filterable by `is_active`, searchable by name/e-mail (`?search=`) and sortable (`?ordering=-created_at`). Visibility rules are evaluated in the service layer.",
        responses={
            200: UserListRetrieveSerializer(many=True),
            401: NotAuthenticatedSerializer,
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return UserService.list_users(requesting_user=self.request.user)


@extend_schema(tags=["Perfil"])
class UserDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get user profile by ID",
        description="Retrieves profile details for a specific user using their ID, provided the requesting user has the necessary permissions.",
        responses={
            200: UserListRetrieveSerializer,
            401: NotAuthenticatedSerializer,
            404: UserNotFoundSerializer,
        },
    )
    def get(self, request, user_id):
        try:
            user = UserService.get_user_by_id(
                target_user_id=user_id, requesting_user=request.user
            )
        except User.DoesNotExist:
            raise NotFound({"detail": MSG_USER_NOT_FOUND})

        serializer = UserListRetrieveSerializer(user)
        return Response(serializer.data, status.HTTP_200_OK)


@extend_schema(tags=["Conta e Sessões"])
class DeactivateSelfView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Deactivate own user account",
        description="Deactivates the authenticated user's account, revoking all active sessions and preventing subsequent authentication attempts.",
        request=None,
        responses={
            200: UserDeactivatedSerializer,
            401: NotAuthenticatedSerializer,
        },
    )
    def post(self, request):
        UserService.deactivate_user(request.user)
        return Response({"detail": MSG_USER_DEACTIVATED}, status.HTTP_200_OK)


@extend_schema(tags=["Perfil"])
class UserUpdateSelfView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Update current user profile",
        description="Performs a partial update on the profile fields of the currently authenticated user.",
        request=UserUpdateSelfSerializer,
        responses={
            200: UserUpdateSelfSerializer,
            400: UserUpdateSelfSerializer,
            401: NotAuthenticatedSerializer,
        },
    )
    def patch(self, request):
        user = request.user
        serializer = UserUpdateSelfSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data, status.HTTP_200_OK)
