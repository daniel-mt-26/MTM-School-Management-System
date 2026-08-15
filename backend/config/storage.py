from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured


LOCAL_STORAGE = {"BACKEND": "django.core.files.storage.FileSystemStorage"}
SUPABASE_REQUIRED_SETTINGS = (
    "SUPABASE_STORAGE_BUCKET",
    "SUPABASE_S3_ENDPOINT",
    "SUPABASE_S3_REGION",
    "SUPABASE_S3_ACCESS_KEY_ID",
    "SUPABASE_S3_SECRET_ACCESS_KEY",
)


def media_storage_config(environment):
    mode = environment.get("MTM_MEDIA_STORAGE", "local").strip().lower()
    if mode == "local":
        return LOCAL_STORAGE.copy()
    if mode != "supabase":
        raise ImproperlyConfigured("MTM_MEDIA_STORAGE must be either 'local' or 'supabase'.")

    missing = [name for name in SUPABASE_REQUIRED_SETTINGS if not environment.get(name)]
    if missing:
        raise ImproperlyConfigured(
            "Supabase media storage is missing required environment variables: " + ", ".join(missing)
        )
    endpoint = environment["SUPABASE_S3_ENDPOINT"]
    if urlparse(endpoint).scheme != "https":
        raise ImproperlyConfigured("SUPABASE_S3_ENDPOINT must use HTTPS.")

    return {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": environment["SUPABASE_STORAGE_BUCKET"],
            "endpoint_url": endpoint.rstrip("/"),
            "region_name": environment["SUPABASE_S3_REGION"],
            "access_key": environment["SUPABASE_S3_ACCESS_KEY_ID"],
            "secret_key": environment["SUPABASE_S3_SECRET_ACCESS_KEY"],
            "addressing_style": "path",
            "signature_version": "s3v4",
            "default_acl": None,
            "querystring_auth": True,
            "querystring_expire": 300,
            "file_overwrite": False,
            "verify": True,
        },
    }
