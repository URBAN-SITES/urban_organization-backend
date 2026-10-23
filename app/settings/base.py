import os
from datetime import timedelta
from pathlib import Path

# from django.contrib import messages
from corsheaders.defaults import default_headers
from dotenv import load_dotenv

load_dotenv()


BASE_DIR = Path(__file__).resolve().parent.parent.parent
# Path to the Firebase service account JSON; empty disables push
FIREBASE_CREDENTIALS = os.getenv("FIREBASE_CREDENTIALS", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
APPEND_SLASH = True
CSRF_HEADER_NAME = "HTTP_X_CSRFTOKEN"
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8000",
    "https://3009.michalski.app",
]
# frontends allowed to call the API; credentials so the auth cookies are sent
CORS_ALLOWED_ORIGINS = CSRF_TRUSTED_ORIGINS
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = (*default_headers, "idempotency-key")
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_NAME = "csrftoken"
SESSION_COOKIE_SAMESITE = "None"
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = False  # TODO: ALTERNAR TRUE EM PRODUÇÃO
INSTALLED_APPS = [
    "daphne",  # makes runserver serve HTTP + WebSocket (ASGI)
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "core",
    "auditlog",
    "django_extensions",
]
LANGUAGES = [
    ("en", "English"),
]
LANGUAGES_BIDI = []
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "default"},
    },
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
}
# who changed what and when, visible in the admin under "Log entries"
AUDITLOG_INCLUDE_TRACKING_MODELS = (
    {"model": "core.User", "exclude_fields": ["password", "last_login"]},
    "core.UserSession",
)
STATIC_URL = "static/"
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.idempotency.IdempotencyMiddleware",
    "core.middleware.audit.AuditlogMiddleware",
]
ROOT_URLCONF = "app.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
TIME_ZONE = "America/Sao_Paulo"
# Django 6.1+ mail config (EMAIL_* settings are deprecated); dev.py overrides it
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": os.getenv("EMAIL_HOST", "smtp.gmail.com"),
            "port": int(os.getenv("EMAIL_PORT", "587")),
            "username": os.getenv("EMAIL_HOST_USER", ""),
            "password": os.getenv("EMAIL_HOST_PASSWORD", ""),
            "use_tls": os.getenv("EMAIL_USE_TLS", "True") == "True",
            "timeout": 10,
        },
    },
}
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "no-reply@localhost")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TIME_LIMIT = 5 * 60
WSGI_APPLICATION = "app.wsgi.application"
ASGI_APPLICATION = "app.asgi.application"
# single process only; use channels_redis.core.RedisChannelLayer in production
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
AUTH_USER_MODEL = "core.User"
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {
            "min_length": 9,
        },
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "core.authenticate.CustomAuthentication",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # request.version comes from the URL namespace ("v1"); add "v2" when needed
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.NamespaceVersioning",
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ["v1"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
        # login and one-time-code endpoints (brute-force protection)
        "auth": "10/minute",
    },
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "CHECK_REVOKE_TOKEN": True,
    "CHECK_USER_IS_ACTIVE": True,
    "AUTH_COOKIE": "access_token",
    "AUTH_COOKIE_DOMAIN": None,
    "AUTH_COOKIE_SECURE": False,
    "AUTH_COOKIE_HTTP_ONLY": True,
    "AUTH_COOKIE_PATH": "/",
    "AUTH_COOKIE_SAMESITE": "Lax",
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Your API",
    "VERSION": "1.0.0",
    "AUTHENTICATION_WHITELIST": [
        "core.authenticate.CustomAuthentication",
    ],
    "TAGS": [
        {"name": "Organizações", "description": "Organizações e seus membros"},
        {
            "name": "Ingressar Em Uma Organização",
            "description": "Convites para ingressar em organizações",
        },
        {"name": "Setores", "description": "Setores e seus quadros Kanban"},
        {"name": "Times", "description": "Gerenciamento de times de uma organização"},
        {"name": "Tarefas", "description": "Tarefas dos quadros"},
        {"name": "Links", "description": "Links de organizações, setores e tarefas"},
        {"name": "Chat", "description": "Mensagens e conversas"},
        {"name": "Notificações", "description": "Notificações e dispositivos"},
        {"name": "Pagamentos", "description": "Pagamentos e webhooks"},
        {"name": "Arquivos", "description": "Uploads e arquivos"},
        {"name": "IA", "description": "Recursos de inteligência artificial"},
        {"name": "Busca", "description": "Busca global"},
        {"name": "Integrações", "description": "Integrações com serviços externos"},
        {"name": "Conta e Sessões", "description": "Gerenciamento de contas e sessões"},
        {"name": "Perfil", "description": "Gerenciamento de perfil"},
        {"name": "Utilitários", "description": "Ferramentas auxiliares"},
    ],
}
