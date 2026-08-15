# MTM deployment preparation

This project is prepared for deployment; it is not deployed by this document.

## Configuration

Set environment values outside Git: `DJANGO_SECRET_KEY`, PostgreSQL connection
variables, `DJANGO_DEBUG=false`, `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`,
`CSRF_TRUSTED_ORIGINS`, and the secure-cookie/HTTPS variables shown in
`backend/.env.example`. Use a real HTTPS reverse proxy and set
`SECURE_SSL_REDIRECT`, secure cookies, and HSTS only after TLS is confirmed.

Serve static/media through suitable production infrastructure. Django's DEBUG
media serving is development-only. Receipt PDFs remain authenticated API
responses and must not be made public media links.

## Vercel and Supabase

Use two Vercel projects from this repository:

- Frontend: set the Vercel Root Directory to `frontend/`; configure
  `VITE_API_BASE_URL` with the deployed Django API URL.
- Backend: use the repository root so Vercel can discover `api/index.py`, the
  root `requirements.txt`, `.python-version`, and `vercel.json`. The adapter
  adds `backend/` to Python's import path and exposes
  `config.wsgi.application` as the Vercel WSGI `app`.

The frontend already defaults to `http://127.0.0.1:8000/api` locally and reads
`VITE_API_BASE_URL` in production. Keep Django JWT authentication and the REST
API as the only browser-facing data layer; Supabase is managed PostgreSQL, not
a client-side replacement for Django permissions.

Set `DATABASE_URL` to the Supabase PostgreSQL connection string in the backend
Vercel environment. If it is absent locally, Django continues to use the
existing `POSTGRES_*` settings. Set production host/origin values through
`DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, and `CSRF_TRUSTED_ORIGINS`.

WhiteNoise serves collected Django static assets only. Vercel's filesystem is
not persistent uploaded-media storage. MTM now selects its Django default media
storage explicitly:

- `MTM_MEDIA_STORAGE=local` uses `backend/media/` and requires no Supabase
  credentials. This is the development default.
- `MTM_MEDIA_STORAGE=supabase` uses `storages.backends.s3.S3Storage` with the
  private Supabase S3-compatible endpoint. Missing variables or a non-HTTPS
  endpoint stop startup rather than falling back to ephemeral local files.

The models that require persistent Django storage are:

- `School.logo` (`ImageField`, `school_logos/`)
- `HomeworkAttachment.file` (`FileField`, `homework/<school>/<homework>/`)
- `ReportCard.file` (`FileField`, `report_cards/`)

Supabase mode uses path-style S3 addressing, Signature Version 4, TLS
verification, no public ACL, no filename overwrites, and authenticated signed
URLs that expire after 300 seconds. Homework and Report Card APIs do not return
raw object URLs; their authenticated Django download actions remain the access
control boundary. School logos currently use Django's short-lived signed URL so
the existing `<img>` UI continues working. A separate public branding bucket is
an optional future refinement, not required for private operational media.

Local development continues using `MEDIA_ROOT`. The existing
`purge_expired_homework_attachments` command must remain the only Homework
retention deletion path: once external storage is configured, its existing
`attachment.file.delete()` call will delete through Django's configured storage
backend. Schedule that command separately because a Vercel web function does
not run persistent background tasks.

Production email is not enabled merely by deploying. Set
`DJANGO_EMAIL_BACKEND` and the `EMAIL_*` variables for an SMTP service; retain
the console backend only for development.

### Manual Supabase Storage prerequisite

1. In Supabase Dashboard, create a private bucket such as
   `mtm-private-media`. Do not make it public.
2. Open **Storage → S3 Configuration**, enable the S3 protocol if required,
   and generate a server-side S3 Access Key ID and Secret Access Key.
3. Record the direct storage endpoint and project region shown by Supabase.
4. Add these variables to the **backend Vercel project only**:

   ```text
   MTM_MEDIA_STORAGE=supabase
   SUPABASE_STORAGE_BUCKET=<private bucket name>
   SUPABASE_S3_ENDPOINT=<HTTPS S3 endpoint>
   SUPABASE_S3_REGION=<project region>
   SUPABASE_S3_ACCESS_KEY_ID=<server-side secret>
   SUPABASE_S3_SECRET_ACCESS_KEY=<server-side secret>
   ```

   Never create `VITE_*` copies of the access key or secret.

Django `FileField` and `ImageField` rows store object keys, not file bytes. Any
existing files under local `backend/media/` whose database values must be kept
in production require a deliberate one-time upload to matching object keys in
the Supabase bucket. Do not run that migration automatically and do not upload
demo media as part of deployment.

## Backups

Run `pg_dump` from a secured operator environment; obtain connection settings
from environment variables or the managed database service, not a script:

```sh
pg_dump --format=custom --file=mtm-backup.dump "$DATABASE_URL"
```

Test restore only against an isolated database:

```sh
pg_restore --clean --if-exists --dbname="$RESTORE_DATABASE_URL" mtm-backup.dump
```

Back up private media separately with its access controls. Never run a restore
against a production database without an approved recovery plan.
