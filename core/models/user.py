import uuid

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    use_in_migrations = True

    def find_by_email(self, email):
        """Case-insensitive lookup; exact match wins, an ambiguous match finds nobody."""
        email = email.strip()
        exact = self.filter(email=email).first()
        if exact:
            return exact
        matches = list(self.filter(email__iexact=email)[:2])
        return matches[0] if len(matches) == 1 else None

    def get_by_natural_key(self, email):
        # accounts created before e-mails were lowercased keep logging in
        user = self.find_by_email(email)
        if user is None:
            raise self.model.DoesNotExist
        return user

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError(_("The given email address must be set."))

        email = email.strip().lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))

        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    name = models.CharField(
        _("name"),
        max_length=255,
        blank=False,
    )

    email = models.EmailField(
        _("email address"),
        unique=True,
        blank=False,
    )

    bio = models.TextField(_("bio"), blank=True)

    avatar_url = models.URLField(_("avatar url"), blank=True)

    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_(
            "Designates whether this user should be treated as active. "
            "Unselect this instead of deleting accounts."
        ),
    )

    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can log into this admin site."),
    )

    created_at = models.DateTimeField(
        _("created at"),
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        _("updated at"),
        auto_now=True,
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    objects = UserManager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} <{self.email}>" if self.name else self.email

    @property
    def is_subscriber(self) -> bool:
        """Existing confirmed payments grant access; no automatic renewal is sold."""
        from core.modules.payments.models.payment import Payment
        from core.modules.payments.services.payment import PAYMENT_AMOUNT

        return (
            self.payments.filter(status=Payment.Status.APPROVED, amount=PAYMENT_AMOUNT)
            .exclude(provider_payment_id="")
            .exists()
        )

    def get_full_name(self) -> str:
        return self.name.strip()

    def get_short_name(self) -> str:
        return self.name.split()[0] if self.name else self.email

    def deactivate(self):
        self.is_active = False
        self.save(update_fields=["is_active", "updated_at"])


from django.conf import settings


class UserSession(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sessions"
    )
    access_jti = models.CharField(max_length=255, unique=True)
    refresh_jti = models.CharField(max_length=255, unique=True)
    device_name = models.CharField(max_length=255)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    location = models.CharField(
        max_length=255,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user} - {self.device_name}"
