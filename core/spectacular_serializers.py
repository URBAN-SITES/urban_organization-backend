from drf_spectacular.utils import inline_serializer
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    PermissionDenied,
)
from rest_framework.serializers import CharField

from core.response_messages import (
    MSG_CANNOT_DEACTIVATE_CURRENT_SESSION,
    MSG_CODE_INVALID,
    MSG_CODE_SENT,
    MSG_CODE_VALID,
    MSG_EMAIL_ALREADY_EXIST,
    MSG_EMAIL_CHANGED,
    MSG_INVALID_OR_EXPIRED_REFRESH_TOKEN,
    MSG_LOGIN_SUCCESSFUL,
    MSG_LOGOUT_SUCCESSFUL,
    MSG_NO_REFRESH_TOKEN_PROVIDED,
    MSG_PASWORD_RESET,
    MSG_REFRESH_TOKENS_SUCCESSFUL,
    MSG_SERVICE_UNAVAILABLE,
    MSG_SESSION_REVOKED_OR_INACTIVE,
    MSG_USER_CREATED,
    MSG_USER_DEACTIVATED,
    MSG_USER_NOT_FOUND,
    MSG_USER_REVOKED_ALL_SESSIONS,
    MSG_USER_SESSION_DEACTIVATED,
    MSG_USER_SESSION_NOT_FOUND,
)

ServiceUnavaibleSerializer = inline_serializer(
    "ServiceUnavaibleSerializer",
    {
        "detail": CharField(default=MSG_SERVICE_UNAVAILABLE),
    },
)

RequestSentSerializer = inline_serializer(
    "RequestSentSerializer",
    {
        "detail": CharField(default=MSG_CODE_SENT),
    },
)

CodeIsValidSerializer = inline_serializer(
    "CodeIsValidSerializer",
    {
        "detail": CharField(default=MSG_CODE_VALID),
    },
)

CodeIsInvalidSerializer = inline_serializer(
    "CodeIsInvalidSerializer",
    {
        "code": CharField(default=MSG_CODE_INVALID),
    },
)

UserCreatedSerializer = inline_serializer(
    "UserCreateSuccessful",
    {
        "detail": CharField(default=MSG_USER_CREATED),
    },
)

EmailAlreadyExistsSerializer = inline_serializer(
    "EmailAlreadyExistsSerializer",
    fields={
        "email": CharField(
            default=MSG_EMAIL_ALREADY_EXIST,
            required=False,
        )
    },
)

PasswordResetSerializer = inline_serializer(
    "PasswordResetConfirmSuccess",
    {
        "detail": CharField(default=MSG_PASWORD_RESET),
    },
)

NotAuthenticatedSerializer = inline_serializer(
    "NotAuthenticatedSerializer",
    {
        "detail": CharField(default=NotAuthenticated().default_detail),
    },
)

IncorrectAuthenticationsCredentialsSerializer = inline_serializer(
    "IncorrectAuthenticationsCredentialsSerializer",
    {
        "detail": CharField(default=AuthenticationFailed().default_detail),
    },
)


PermissionDeniedSerializer = inline_serializer(
    "PermissionDeniedSerializer",
    {
        "detail": CharField(default=PermissionDenied().default_detail),
    },
)

NewEmailAlreadyExistsSerializer = inline_serializer(
    "NewEmailAlreadyExistsSerializer",
    fields={
        "new-email": CharField(
            default=MSG_EMAIL_ALREADY_EXIST,
        )
    },
)

NewEmailChangedSerializer = inline_serializer(
    "NewEmailChangedSerializer",
    fields={
        "new-email": CharField(
            default=MSG_EMAIL_CHANGED,
        )
    },
)

UserDeactivatedSerializer = inline_serializer(
    "UserDeactivatedSerializer",
    {
        "detail": CharField(default=MSG_USER_DEACTIVATED),
    },
)

UserRevokedAllSessionsSerializer = inline_serializer(
    "UserRevokedAllSessionsSerializer",
    {
        "detail": CharField(default=MSG_USER_REVOKED_ALL_SESSIONS),
    },
)

LoginSucessfulSerializer = inline_serializer(
    "LoginSuccsesfulResponse",
    {"detail": CharField(default=MSG_LOGIN_SUCCESSFUL)},
)

LogoutSuccessfulSerializer = inline_serializer(
    "LogoutSuccessfulResponse",
    {"detail": CharField(default=MSG_LOGOUT_SUCCESSFUL)},
)

UserSessionDeactivatedSerializer = inline_serializer(
    "UserSessionDeactivatedSerializer",
    {"detail": CharField(default=MSG_USER_SESSION_DEACTIVATED)},
)

UserSessionNotFoundSerializer = inline_serializer(
    "UserSessionNotFoundSerializer",
    {"detail": CharField(default=MSG_USER_SESSION_NOT_FOUND)},
)


UserNotFoundSerializer = inline_serializer(
    "UserNotFoundSerializer",
    {"detail": CharField(default=MSG_USER_NOT_FOUND)},
)

CannotDeactivateCurrentSessionSerializer = inline_serializer(
    "CannotDeactivateCurrentSessionSerializer",
    {
        "detail": CharField(default=MSG_CANNOT_DEACTIVATE_CURRENT_SESSION),
    },
)


RefreshTokensSuccessfulSerializer = inline_serializer(
    "RefreshTokensSuccessfulSerializer",
    {
        "detail": CharField(default=MSG_REFRESH_TOKENS_SUCCESSFUL),
    },
)
NoRefreshTokenProvidedSerializer = inline_serializer(
    "NoRefreshTokenProvidedSerializer",
    {
        "detail": CharField(default=MSG_NO_REFRESH_TOKEN_PROVIDED),
    },
)

InvalidOrExpiredRefreshTokenSerializer = inline_serializer(
    "InvalidOrExpiredRefreshTokenSerializer",
    {
        "detail": CharField(default=MSG_INVALID_OR_EXPIRED_REFRESH_TOKEN),
    },
)

SessionRevokedOrInactiveSerializer = inline_serializer(
    "SessionRevokedOrInactiveSerializer",
    {
        "detail": CharField(default=MSG_SESSION_REVOKED_OR_INACTIVE),
    },
)
