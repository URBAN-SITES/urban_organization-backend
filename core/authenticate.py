from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import exceptions
from rest_framework.authentication import CSRFCheck
from rest_framework_simplejwt.authentication import JWTAuthentication

from core.models.user import UserSession


def dummy_get_response(request):
    return None


def enforce_csrf(request):
    check = CSRFCheck(dummy_get_response)
    check.process_request(request)
    reason = check.process_view(request, None, (), {})
    if reason:
        raise exceptions.PermissionDenied(f"CSRF Failed: {reason}")


class CustomAuthentication(JWTAuthentication):
    def authenticate(self, request):

        # ===========================================================
        # Permite que a autenticação seja consumida de várias formas.
        # Esse trecho comentado tenta buscar o cookie no cabeçalho: 'Authorization: Bearer <token>'.
        # Se ele não encontra, pega dos cookies enviados pela requisição.
        # ===========================================================
        # header = self.get_header(request)
        # if header is None:
        #     cookie_name = settings.SIMPLE_JWT.get("AUTH_COOKIE", "access_token")
        #     raw_token = request.COOKIES.get(cookie_name)
        #     if raw_token:
        #         is_cookie_auth = True
        #     else:
        #         raw_token = None
        # else:
        #     raw_token = self.get_raw_token(header)
        # if raw_token is None:
        #     return None

        is_cookie_auth = False
        cookie_name = settings.SIMPLE_JWT.get("AUTH_COOKIE", "access_token")
        raw_token = request.COOKIES.get(cookie_name)
        if raw_token:
            is_cookie_auth = True
        else:
            raw_token = None

        # =======================================================
        # Retorna None e indica para o DRF que o usuário é anônimo.
        # É mais um fallback para caso tenha esquecido de declarar 'authentication_classes = []',
        # nas classes das views públicas como a classe da view de login.

        if raw_token is None:
            return None
        # =======================================================

        validated_token = self.get_validated_token(raw_token)
        if not self.is_session_active(validated_token):
            raise exceptions.AuthenticationFailed()
        if is_cookie_auth and request.method not in (
            "GET",
            "HEAD",
            "OPTIONS",
        ):
            enforce_csrf(request)
        return self.get_user(validated_token), validated_token

    @staticmethod
    def is_session_active(validated_token):
        jti = str(validated_token.get("jti", ""))
        return UserSession.objects.filter(access_jti=jti, is_active=True).exists()


class CustomAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "core.authenticate.CustomAuthentication"
    name = "customCookieAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "cookie",
            "name": settings.SIMPLE_JWT.get("AUTH_COOKIE", "access_token"),
        }
