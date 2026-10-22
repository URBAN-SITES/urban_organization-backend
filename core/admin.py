from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as UserAdminFromDjango
from django.utils.translation import gettext_lazy as _

from core.models.email_change import EmailChange
from core.models.email_verification import EmailVerification
from core.models.password_reset import PasswordReset
from core.models.user import User, UserSession
from core.modules.notifications import admin as _notifications_admin  # noqa: F401
from core.modules.payments import admin as _payments_admin  # noqa: F401


class NoAddModelAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False


@admin.register(User)
class UserAdmin(UserAdminFromDjango):
    ordering = ("-created_at",)

    list_display = (
        "email",
        "name",
        "is_active",
        "is_staff",
        "is_superuser",
        "created_at",
    )

    list_filter = (
        "is_active",
        "is_staff",
        "is_superuser",
        "groups",
        "created_at",
    )

    search_fields = (
        "name",
        "email",
        "groups__name",
        "user_permissions__name",
        "user_permissions__codename",
    )

    readonly_fields = (
        "id",
        "last_login",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            _("Identification"),
            {
                "fields": (
                    "id",
                    "name",
                    "email",
                    "password",
                )
            },
        ),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                )
            },
        ),
        (
            _("Important dates"),
            {
                "fields": (
                    "last_login",
                    "created_at",
                    "updated_at",
                )
            },
        ),
        (
            _("Groups & Permissions"),
            {
                "classes": ("collapse",),
                "fields": (
                    "groups",
                    "user_permissions",
                ),
            },
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "name",
                    "password1",
                    "password2",
                ),
            },
        ),
    )


class OneTimeCodeAdmin(NoAddModelAdmin):
    list_display = (
        "user",
        "attempts",
        "used",
        "created_at",
        "expires_at",
    )

    readonly_fields = (
        "id",
        "user",
        "used",
        "used_at",
        "attempts",
        "created_at",
        "expires_at",
    )

    fieldsets = (
        (
            _("User Info"),
            {
                "fields": (
                    "id",
                    "user",
                )
            },
        ),
        (
            _("Usage Status"),
            {
                "fields": (
                    "used",
                    "used_at",
                    "attempts",
                )
            },
        ),
        (
            _("Validity Dates"),
            {
                "fields": (
                    "created_at",
                    "expires_at",
                )
            },
        ),
    )

    list_filter = (
        "used",
        "created_at",
        "expires_at",
    )

    search_fields = (
        "user__email",
        "user__name",
    )


@admin.register(EmailVerification)
class EmailVerificationAdmin(OneTimeCodeAdmin):
    pass


@admin.register(PasswordReset)
class PasswordResetAdmin(OneTimeCodeAdmin):
    pass


@admin.register(EmailChange)
class EmailChangeAdmin(OneTimeCodeAdmin):
    list_display = (
        "user",
        "new_email",
        "attempts",
        "used",
        "created_at",
    )

    readonly_fields = OneTimeCodeAdmin.readonly_fields + ("new_email",)

    fieldsets = (
        (
            _("User Info"),
            {
                "fields": (
                    "id",
                    "user",
                    "new_email",
                )
            },
        ),
        (
            _("Usage Status"),
            {
                "fields": (
                    "used",
                    "used_at",
                    "attempts",
                )
            },
        ),
        (
            _("Validity Dates"),
            {
                "fields": (
                    "created_at",
                    "expires_at",
                )
            },
        ),
    )

    search_fields = OneTimeCodeAdmin.search_fields + ("new_email",)


@admin.register(UserSession)
class UserSessionAdmin(NoAddModelAdmin):
    list_display = (
        "user",
        "device_name",
        "ip_address",
        "is_active",
        "created_at",
        "last_activity",
    )

    list_filter = (
        "is_active",
        "created_at",
        "last_activity",
    )

    search_fields = (
        "user__email",
        "user__name",
        "device_name",
        "ip_address",
    )

    readonly_fields = (
        "user",
        "access_jti",
        "refresh_jti",
        "device_name",
        "ip_address",
        "location",
        "created_at",
        "last_activity",
    )
