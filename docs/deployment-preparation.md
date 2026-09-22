# MTM production deployment preparation

MTM SMS uses the Vite/React frontend on Vercel, the Django API on Render, and Supabase for PostgreSQL and private media storage. This document prepares deployment only. It does not deploy, migrate, restore, or provision school data.

## Repository layout

| Component | Location | Production configuration |
| --- | --- | --- |
| React frontend | `frontend/` | Vercel project with Root Directory `frontend/` |
| Django API | `backend/` | Render Blueprint `render.yaml` |
| Django settings / WSGI | `backend/config.settings` / `backend/config.wsgi:application` | Gunicorn process |
| Dependencies | `backend/requirements.txt` | Render build installs them |
| Database and media | Supabase | PostgreSQL `DATABASE_URL` and private S3 storage |

Django exposes `GET /api/health/` and `GET /api/health/ready/`. Render uses the readiness route after the release migration command completes.

## Render dashboard values

Create a Render Blueprint from this repository using `render.yaml`. It creates the `mtm-sms-api` Python web service with these values:

| Render field | Value |
| --- | --- |
| Root Directory | `backend` |
| Build Command | `pip install -r requirements.txt && python manage.py collectstatic --noinput` |
| Pre-deploy Command | `python manage.py migrate --noinput` |
| Start Command | `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 3 --timeout 120` |
| Health Check Path | `/api/health/ready/` |
| Auto deploy | Disabled until a release is approved |

Set the following Render variables. Enter actual values only in Render; `backend/.env.production.example` contains names and safe placeholders only.

| Variable | Required value format |
| --- | --- |
| `DJANGO_ENV` | `production` |
| `DJANGO_DEBUG` | `false` |
| `DJANGO_SECRET_KEY` | Render-generated or securely generated secret |
| `DATABASE_URL` | Supabase **Session Pooler** URI with `sslmode=require` |
| `DB_CONN_MAX_AGE` | `0` |
| `DB_SSL_REQUIRE` | `true` |
| `DJANGO_ALLOWED_HOSTS` | Render hostname, for example `mtm-sms-api.onrender.com` |
| `CORS_ALLOWED_ORIGINS` | Comma-separated HTTPS Vercel production/custom origins |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated HTTPS Vercel production/custom origins |
| `SECURE_SSL_REDIRECT` | `true` |
| `SESSION_COOKIE_SECURE` | `true` |
| `CSRF_COOKIE_SECURE` | `true` |
| `SECURE_HSTS_SECONDS` | `31536000` after HTTPS hostname verification |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS`, `SECURE_HSTS_PRELOAD` | `false` initially; enable only when their domain commitments are intended |
| `JWT_ACCESS_MINUTES`, `JWT_REFRESH_DAYS`, `JWT_ROTATE_REFRESH_TOKENS`, `JWT_BLACKLIST_AFTER_ROTATION` | Existing JWT policy values |
| `MTM_N8N_INTEGRATION_SECRET`, `MTM_OUTBOX_CLAIM_TIMEOUT_SECONDS`, `MTM_OUTBOX_MAX_ATTEMPTS` | Existing n8n/outbox policy |
| `DJANGO_EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL` | Production SMTP values; console email is not email recovery |
| `MTM_MEDIA_STORAGE` | `supabase` |
| `SUPABASE_STORAGE_BUCKET`, `SUPABASE_S3_ENDPOINT`, `SUPABASE_S3_REGION`, `SUPABASE_S3_ACCESS_KEY_ID`, `SUPABASE_S3_SECRET_ACCESS_KEY` | Private Supabase S3 storage values |

In production Django fails startup if the database URL, hosts, CORS origins, or CSRF trusted origins are missing; if debug is enabled; or if database SSL is disabled. Render terminates TLS before Django, so the app trusts `X-Forwarded-Proto` and enforces secure redirects and cookies.

## Supabase

Use the Supabase **Session Pooler** connection string for Render, with TLS required. Select Session Pooler in the Supabase dashboard and preserve its generated host, port, user, database, and `sslmode=require`; do not construct a connection string by changing a direct connection port.

Create a private Supabase Storage bucket before setting `MTM_MEDIA_STORAGE=supabase`. Storage credentials stay in Render only. School logos, homework attachments, and report cards must not be made public.

Before a release that runs migrations, create a custom-format PostgreSQL backup from a secured operator environment and verify the archive can be read. Never restore local `mtm_sms` into Supabase.

## Vercel frontend

Create one Vercel project with Root Directory `frontend/`. After Render supplies the public API URL, set this Vercel production variable:

```text
VITE_API_BASE_URL=https://<render-public-hostname>/api
```

The frontend reads `VITE_API_BASE_URL`; do not use `VITE_API_URL`. Never expose Supabase keys, Django secrets, database URLs, SMTP credentials, or n8n secrets as `VITE_*` values. Add the Vercel production URL and each custom frontend domain to Render's `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS`.

## Approved release sequence

1. Create and verify the Supabase backup.
2. Confirm Render variables and its HTTPS public URL.
3. Set Vercel `VITE_API_BASE_URL` to the Render URL plus `/api`.
4. Deploy the approved commit; Render runs migrations before starting Gunicorn.
5. Verify actual HTTPS health and CORS responses from the Vercel origin, then test login, `/auth/me/`, and tenant isolation.
6. Provision a school only after separate approval. Infrastructure deployment must not import local data or create learner or financial records.
