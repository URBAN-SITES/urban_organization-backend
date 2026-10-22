import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings.prod")

# Django must be set up before importing code that touches models
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402
from channels.sessions import CookieMiddleware  # noqa: E402

from core.websockets.auth import JWTCookieAuthMiddleware  # noqa: E402
from core.websockets.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            CookieMiddleware(JWTCookieAuthMiddleware(URLRouter(websocket_urlpatterns)))
        ),
    }
)
