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
