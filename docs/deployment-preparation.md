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
not persistent uploaded-media storage. Before production, configure Django's
default storage backend for a private Supabase Storage bucket. The models that
currently require persistent Django storage are:

- `School.logo` (`ImageField`, `school_logos/`)
- `HomeworkAttachment.file` (`FileField`, `homework/<school>/<homework>/`)
- `ReportCard.file` (`FileField`, `report_cards/`)

Local development continues using `MEDIA_ROOT`. The existing
`purge_expired_homework_attachments` command must remain the only Homework
retention deletion path: once external storage is configured, its existing
`attachment.file.delete()` call will delete through Django's configured storage
backend. Schedule that command separately because a Vercel web function does
not run persistent background tasks.

Production email is not enabled merely by deploying. Set
`DJANGO_EMAIL_BACKEND` and the `EMAIL_*` variables for an SMTP service; retain
the console backend only for development.

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
