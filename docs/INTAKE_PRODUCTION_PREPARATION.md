# Intake backend production preparation — 13 October 2026

Prepared on branch `deploy/render-production`. This release includes the intake backend and its required registration, configuration, email templates, tests and operations documentation. Existing frontend changes and the unrelated attendance report are excluded.

## Validation

- Django `check`: no issues.
- `makemigrations --check --dry-run`: no changes detected.
- Migration graph: `0021_timetable_scope` → `0022_intake_admissions_enquiries` → `0023_intake_retention_lifecycle`.
- All 53 intake API, email, retention and concurrency tests pass on a disposable local PostgreSQL test database. Tests use synthetic data, mocked provider calls and a test-only fast password hasher.
- Deployment checks with synthetic production security flags and SMTP configuration report only `security.W005` and `security.W021`. Subdomain HSTS and preload are intentionally disabled in `render.yaml`; enable them only after domain-wide HTTPS review. The local console email backend fails production deployment checks, as expected. Configure production SMTP; do not copy local settings.
- Migrations 0022 and 0023 are pending on the local application database. Only the disposable test database was migrated. Production migration status was not queried.
- Public intake defaults to disabled in settings and `.env.intake.example`. No deployment configuration or local environment file was changed.

## Retention compatibility

Rejected applications and resolved enquiries expire one calendar month after transition, using Africa/Harare time and month-end clamping. Pending/approved applications and unresolved enquiries have no expiry. Reopening clears expiry; notes and repeated terminal statuses do not restart it. Technical replay key expiry is separate. Cleanup requires eligible status, elapsed expiry and no preservation hold; it locks schools in a consistent order with review/submission transactions. These global school locks can briefly delay other school operations, so schedule any future approved purge during low traffic.

Migration 0023 clears old submission-based deadlines, then reconstructs terminal deadlines from transition history. Missing decision evidence remains unexpired for manual review. Existing holds remain intact. The data migration is irreversible; backup restoration or a reviewed forward repair is needed to undo it. Approved applications remain preserved because verified transfer and recordkeeping disposition are not implemented.

## Scheduler findings and pause procedure

`render.yaml` defines only the API service and has automatic deploy disabled. No retention cron is defined in the repository. The separate `render-intake-email-cron.example.yaml` is an opt-in email example, not a retention worker. No matching Windows scheduled task was found. The live Render account and any external scheduler were unavailable, so their schedule/status must be verified by the operator before deployment.

Before migration, locate every job whose command includes `purge_intake_records` or a wrapper invoking it. Suspend that specific service in Render (API operation: `POST /v1/services/{serviceId}/suspend`), or disable its external scheduler entry. Confirm no active execution remains; wait for any active purge to finish before migration. Disabling `MTM_INTAKE_ENABLED` does not disable cleanup. Do not trigger a run to pause it. Keep any old intake email worker paused through schema/code rollout as well.

References: [Render suspend API](https://api-docs.render.com/reference/suspend-service), [Render cron jobs](https://render.com/docs/cronjobs).

## Exact operator next steps — not performed here

1. Verify live automatic deployment is off and `MTM_INTAKE_ENABLED=false`. Confirm the selected commit, production database and backup/restore plan. This Git push does not authorize deployment.
2. Inspect live retention/email workers, pause applicable jobs and confirm none is executing. Keep intake review traffic quiescent during migration backfill.
3. After deployment approval, deploy the prepared commit. The existing Render pre-deploy command is `python manage.py migrate --noinput`; it will apply pending migrations, including 0022 then 0023. Do not separately run migrations twice or start the new backend against the old schema.
4. Verify `python manage.py showmigrations core` shows 0022 and 0023 applied. Run production `python manage.py check --deploy` and verify health, authenticated tenant scope and public submissions returning unavailable. Keep the public flag false.
5. Review historical rejected/resolved deadlines, missing-evidence records, preservation holds and approved-record preservation. Backups need their own retention policy.
6. Only after separate cleanup approval, review `python manage.py purge_intake_records` (dry-run). Do not use `--execute` or resume a deletion schedule until the reported candidates and preservation requirements are approved.

No production deployment, production migrations, application-data cleanup, public intake activation or branch merge was performed during preparation. No secrets or local environment files belong in this release; `.env.intake.example` contains disabled flags and blank credential placeholders only.
