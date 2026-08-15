"""Django settings for the MTM School Management System."""

import os
from pathlib import Path
from datetime import timedelta

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [value.strip() for value in os.getenv(name, default).split(",") if value.strip()]

# The actual value is supplied only by the ignored backend/.env or deployment
# environment. Never commit it to this repository.
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY must be configured in the environment.")

DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [], "APP_DIRS": True, "OPTIONS": {"context_processors": ["django.template.context_processors.request", "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages"]}}]
WSGI_APPLICATION = "config.wsgi.application"

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=int(os.getenv("DB_CONN_MAX_AGE", "0")),
            conn_health_checks=True,
            ssl_require=env_bool("DB_SSL_REQUIRE", not DEBUG),
        )
    }
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": os.getenv("POSTGRES_DB", "mtm_sms"), "USER": os.getenv("POSTGRES_USER", "postgres"), "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""), "HOST": os.getenv("POSTGRES_HOST", "localhost"), "PORT": os.getenv("POSTGRES_PORT", "5432")}}

AUTH_USER_MODEL = "core.User"
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_THROTTLE_CLASSES": ("rest_framework.throttling.AnonRateThrottle", "rest_framework.throttling.UserRateThrottle"),
    "DEFAULT_THROTTLE_RATES": {"anon": "120/hour", "user": "1200/hour", "login": "10/minute", "integration": "120/minute"},
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
}
SIMPLE_JWT = {"ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.getenv("JWT_ACCESS_MINUTES", "15"))), "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.getenv("JWT_REFRESH_DAYS", "7"))), "ROTATE_REFRESH_TOKENS": env_bool("JWT_ROTATE_REFRESH_TOKENS", False), "BLACKLIST_AFTER_ROTATION": env_bool("JWT_BLACKLIST_AFTER_ROTATION", False)}
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
AUTH_PASSWORD_VALIDATORS = [{"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"}, {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"}, {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"}, {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"}]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
HOMEWORK_RETENTION_TIME_ZONE = os.getenv("HOMEWORK_RETENTION_TIME_ZONE", "Africa/Johannesburg")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
MAILER_BACKEND = os.getenv("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
MAILERS = {"default": {"BACKEND": MAILER_BACKEND}}
if MAILER_BACKEND == "django.core.mail.backends.smtp.EmailBackend":
    MAILERS["default"]["OPTIONS"] = {
        "host": os.getenv("EMAIL_HOST", ""),
        "port": int(os.getenv("EMAIL_PORT", "587")),
        "username": os.getenv("EMAIL_HOST_USER", ""),
        "password": os.getenv("EMAIL_HOST_PASSWORD", ""),
        "use_tls": env_bool("EMAIL_USE_TLS", True),
    }
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", os.getenv("EMAIL_HOST_USER", "") or "webmaster@localhost")

# n8n uses this server-to-server credential; it is never sent to React or
# stored in the database. A blank value deliberately disables integration APIs.
MTM_N8N_INTEGRATION_SECRET = os.getenv("MTM_N8N_INTEGRATION_SECRET", "")
MTM_OUTBOX_CLAIM_TIMEOUT_SECONDS = int(os.getenv("MTM_OUTBOX_CLAIM_TIMEOUT_SECONDS", "900"))
MTM_OUTBOX_MAX_ATTEMPTS = int(os.getenv("MTM_OUTBOX_MAX_ATTEMPTS", "5"))
MTM_APP_VERSION = os.getenv("MTM_APP_VERSION", "5.8")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", False)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", False)
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": os.getenv("DJANGO_LOG_LEVEL", "WARNING"), "propagate": False},
        "core": {"handlers": ["console"], "level": os.getenv("DJANGO_LOG_LEVEL", "WARNING"), "propagate": False},
    },
}
