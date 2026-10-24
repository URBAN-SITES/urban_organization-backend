from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

from core.views.csrf import CsrfView
from core.views.email_change import (
    EmailChangeConfirmView,
    EmailChangeRequestView,
    EmailChangeVerifyView,
)
from core.views.google_auth import GoogleLoginView
from core.views.password_reset import (
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PasswordResetVerifyView,
)
from core.views.qrcode import QRCodeView
from core.views.registration import (
    RegistrationConfirmView,
    RegistrationRequestView,
    RegistrationVerifyView,
)
from core.views.user import (
    CustomTokenRefreshView,
    DeactivateSelfView,
    LoginView,
    LogoutView,
    RevokeAllSessionsView,
    UserDetailView,
    UserListView,
    UserMeView,
    UserSessionsDeactivateView,
    UserSessionsGetView,
    UserUpdateSelfView,
)

route_docs = [
    path(
        "urls/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
]

route_core = [
    path("csrf/", CsrfView.as_view(), name="csrf"),
    path("login/", LoginView.as_view(), name="login"),
    path("login/google/", GoogleLoginView.as_view(), name="login-google"),
    path("me/logout/", LogoutView.as_view(), name="logout"),
    path("me/deactivate/", DeactivateSelfView.as_view(), name="deactivate-self"),
    path(
        "me/revoke-sessions/", RevokeAllSessionsView.as_view(), name="revoke-sessions"
    ),
    path("sessions/", UserSessionsGetView.as_view(), name="user-sessions-list"),
    path(
        "sessions/<int:session_id>/",
        UserSessionsDeactivateView.as_view(),
        name="user-sessions-deactivate",
    ),
    path(
        "registration/",
        include(
            [
                path(
                    "request/",
                    RegistrationRequestView.as_view(),
                    name="registration-request",
                ),
                path(
                    "verify/",
                    RegistrationVerifyView.as_view(),
                    name="registration-verify",
                ),
                path(
                    "confirm/",
                    RegistrationConfirmView.as_view(),
                    name="registration-confirm",
                ),
            ]
        ),
    ),
    path(
        "password-reset/",
        include(
            [
                path(
                    "request/",
                    PasswordResetRequestView.as_view(),
                    name="password-reset-request",
                ),
                path(
                    "verify/",
                    PasswordResetVerifyView.as_view(),
                    name="password-reset-verify",
                ),
                path(
                    "confirm/",
                    PasswordResetConfirmView.as_view(),
                    name="password-reset-confirm",
                ),
            ]
        ),
    ),
    path(
        "email-change/",
        include(
            [
                path(
                    "request/",
                    EmailChangeRequestView.as_view(),
                    name="email-change-request",
                ),
                path(
                    "verify/",
                    EmailChangeVerifyView.as_view(),
                    name="email-change-verify",
                ),
                path(
                    "confirm/",
                    EmailChangeConfirmView.as_view(),
                    name="email-change-confirm",
                ),
            ]
        ),
    ),
    path("refresh/", CustomTokenRefreshView.as_view(), name="refresh"),
    path("ai/", include("core.modules.ai.urls")),
    path("uploads/", include("core.modules.uploads.urls")),
    path("notifications/", include("core.modules.notifications.urls")),
    path("payments/", include("core.modules.payments.urls")),
    path("organizations/", include("core.modules.organizations.urls")),
    path(
        "organizations/<uuid:organization_id>/teams/",
        include("core.modules.teams.urls"),
    ),
    path("", include("core.modules.invitations.urls")),
    path("", include("core.modules.kanban.urls")),
    path("", include("core.modules.chat.urls")),
    path("", include("core.modules.search.urls")),
    path("", include("core.modules.crowdfunding.urls")),
    path("integrations/google/", include("core.modules.calendar_sync.urls")),
    path("qrcode/", QRCodeView.as_view(), name="qrcode"),
    path("users/me/", UserMeView.as_view(), name="me"),
    path("users/me/settings/", include("core.modules.user_settings.urls")),
    path("users/me/update/", UserUpdateSelfView.as_view(), name="me-update"),
    path("users/list/", UserListView.as_view(), name="users-list"),
    path("users/<uuid:user_id>/", UserDetailView.as_view(), name="user-detail"),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/docs/", include(route_docs)),
    path("api/v1/", include((route_core, "v1"), namespace="v1")),
]
