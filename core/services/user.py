from django.contrib.auth import authenticate
from django.db.models import Q
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from user_agents import parse

from core.models.user import User, UserSession


class SessionService:
    @staticmethod
    def get_active_sessions_with_current(user, raw_access_token):
        sessions = UserSession.objects.filter(user=user, is_active=True)
        current_access_jti = None

        if raw_access_token:
            try:
                current_access_jti = str(AccessToken(raw_access_token).get("jti", ""))
            except TokenError:
                pass

        for session in sessions:
            session.current = bool(
                current_access_jti and str(session.access_jti) == current_access_jti
            )

        return sessions

    @staticmethod
    def deactivate_session(user, session_id):
        session = UserSession.objects.get(id=session_id, user=user)
        try:
            if session.refresh_jti:
                outstanding_token = OutstandingToken.objects.get(
                    jti=session.refresh_jti
                )
                BlacklistedToken.objects.get_or_create(token=outstanding_token)
        except OutstandingToken.DoesNotExist:
            pass

        session.is_active = False
        session.save(update_fields=["is_active"])

    @staticmethod
    def deactivate_session_by_access_jti(user, access_jti):
        session = UserSession.objects.filter(access_jti=access_jti, user=user).first()

        if session:
            try:
                if session.refresh_jti:
                    outstanding_token = OutstandingToken.objects.get(
                        jti=session.refresh_jti
                    )
                    BlacklistedToken.objects.get_or_create(token=outstanding_token)
            except OutstandingToken.DoesNotExist:
                pass

            session.is_active = False
            session.save(update_fields=["is_active"])

    @staticmethod
    def revoke_all_sessions(user):
        tokens = OutstandingToken.objects.filter(user=user)
        for token in tokens:
            BlacklistedToken.objects.get_or_create(token=token)
        UserSession.objects.filter(user=user, is_active=True).update(is_active=False)

    @classmethod
    def update_session_jtis(
        cls, old_refresh_jti: str, new_access_jti: str, new_refresh_jti: str
    ):
        session = UserSession.objects.filter(
            refresh_jti=old_refresh_jti, is_active=True
        ).first()

        if session:
            session.access_jti = new_access_jti
            session.refresh_jti = new_refresh_jti
            session.save(update_fields=["access_jti", "refresh_jti", "updated_at"])
            return session

        return None


class AuthService:
    @staticmethod
    def login_user(email, password, user_agent_string, ip_address):
        user = authenticate(email=email, password=password)

        if not user or not user.is_active:
            raise AuthenticationFailed()
        return AuthService.create_session(user, user_agent_string, ip_address)

    @staticmethod
    def create_session(user, user_agent_string, ip_address):
        """Issues JWTs and records the session. Shared by every login method."""
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)
        user_agent = parse(user_agent_string)
        jti_access = str(AccessToken(access_token).get("jti"))
        jti_refresh = str(RefreshToken(refresh_token).get("jti"))

        UserSession.objects.update_or_create(
            user=user,
            device_name=f"{user_agent.browser.family} on {user_agent.os.family}",
            ip_address=ip_address,
            defaults={
                "access_jti": jti_access,
                "refresh_jti": jti_refresh,
                "is_active": True,
            },
        )

        return {
            "refresh": refresh_token,
            "access": access_token,
        }


class UserService:
    @staticmethod
    def get_user_by_id(target_user_id, requesting_user: User) -> User:
        if requesting_user.is_staff or requesting_user.is_superuser:
            return User.objects.get(pk=target_user_id)
        return User.objects.get(
            Q(pk=target_user_id) & (Q(is_active=True) | Q(pk=requesting_user.pk))
        )

    @staticmethod
    def list_users(requesting_user: User):
        if requesting_user.is_staff or requesting_user.is_superuser:
            return User.objects.all()
        return User.objects.filter(is_active=True)

    @staticmethod
    def deactivate_user(requesting_user: User):
        requesting_user.deactivate()
