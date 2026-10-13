# Online admissions and contact enquiries: Phase 1

Implemented in the existing MTM Django core app and PostgreSQL database. No separate application database or authentication system was created. No Beavers or MDS website files were modified, no deployment or GitHub push was performed, and no production migrations were applied. Existing unrelated working-tree changes were preserved.

## Models and migration

New models are defined in backend/core/intake_models.py and registered through core/models.py:

- AdmissionApplication: UUID, unpredictable APP reference, protected school FK, requested pupil/guardian/contact/address fields, optional previous school/information, pending/approved/rejected status, server consent timestamp, policy version, timestamps, reviewer/review timestamp, retention expiry and concurrency version.
- ContactEnquiry: UUID, unpredictable ENQ reference, school FK, contact/subject/message fields, new/in_progress/resolved status, consent/policy/timestamps, assigned school administrator, retention expiry and version.
- AdmissionReviewHistory and EnquiryHandlingHistory: private append-only API history, actor, statuses, notes, version, timestamp and enquiry assignment.
- PublicIntakeKey: school/kind/UUID scoped key, keyed canonical payload digest, reference and expiry. It is independent of existing authenticated IdempotencyRecord.
- IntakeRateBucket: database-shared atomic fixed-window quotas with pseudonymised keys and expiry.
- IntakeEmailOutbox: one application or enquiry, unique school/acknowledgement purpose, recipient, pending/sending/sent/failed status, retry scheduling, attempts, lease token and safe failure code.

Migration: backend/core/migrations/0022_intake_admissions_enquiries.py, dependent on 0021_timetable_scope. It creates only new intake tables, indexes and constraints. It does not modify Student, Parent or StudentEnrollment behavior. Approval never creates learner, parent or enrolment records.

## Endpoints

Public, anonymous, JSON create-only endpoints:

- POST /api/public/beavers/applications/
- POST /api/public/beavers/enquiries/

Both require a UUID Idempotency-Key header. School ownership is derived solely from MTM_INTAKE_BEAVERS_SCHOOL_ID. No client school ID, reviewer, status, user ID, unknown body fields or query parameters are accepted. Public responses contain saved=true, an opaque reference and queued notification/acknowledgement states only after a committed transaction. Identical validated retries return 200 with the original confirmation; new submissions return 201; conflicting reuse returns 409. No private payload or user/student lookup is exposed publicly. Challenge/honeypot fields are not persisted.

Application payload uses the existing website names: studentName, dateOfBirth (ISO date), grade (ECDA/ECDB/Grade 1-7), guardianName, phone, email, address, optional previousSchool/additionalInformation, consent (literal JSON true), privacyPolicyVersion, optional blank website honeypot and challengeToken when required.

Enquiry payload: fullName, phone, email, subject, message, consent, privacyPolicyVersion, optional blank website and required production challengeToken.

Authenticated school administrator endpoints:

- GET /api/school/applications/ and /api/school/applications/{uuid}/
- POST /api/school/applications/{uuid}/review/
- GET /api/school/applications/{uuid}/history/
- Equivalent list/detail/review/history endpoints under /api/school/enquiries/.

Lists and histories are paginated (25). Optional status filtering is supported. Detail responses use snake_case MTM field names. Review requests require the current integer version and optionally status/private note; enquiries may include assignedAdministratorId (a SchoolAdministrator profile ID, not a user ID), or null to clear it. A stale version returns 409. Notes-only updates are allowed and audited. History is read-only through the API; no generic create/update/delete route is supplied. Administrative responses use Cache-Control: no-store, private.

## Tenant isolation and transactions

Existing MTMJWTAuthentication, IsSchoolAdministrator and SchoolScopedQuerysetMixin are reused. Revoked tokens, suspended schools, forced password changes and wrong roles remain denied. Cross-school detail/history/review requests resolve through scoped querysets and return 404. Related assignment profiles must belong to the same school and be active administrators. Services check actor membership defensively and lock both school and record for review. Versions, history and audit updates are committed together.

Submissions lock the configured school, recheck active/non-demo status, reserve the unique submission key, enforce recipient quotas and commit the intake record, two outbox jobs and metadata-only audit entry together. Database failures return a safe 503 and do not return a saved reference. Idempotency protects retries within its configured retention window, not every possible repeat application with a new key. No claim of automatic duplicate learner matching or enrolment is made.

## Security and production gates

Submissions are disabled by default. They fail closed without an enabled flag, verified tenant binding, approved privacy flag/version, a positive technical key retention period and approved origins. Production additionally requires HTTPS, PostgreSQL and configured server-side Turnstile verification. The operator must verify the real Beavers database PK; registration number 8742 is not a database school ID and was not used as one.

Strict serializers enforce text types, required fields, email/phone formats, maximum lengths, supported grades, real/non-future birth dates, explicit consent and current policy version. JSON parsing rejects duplicate fields and nonstandard constants, limits reads to 16 KiB by default and returns 413 for oversize input. Public endpoints use no MTM JWTs or browser credentials and accept POST/OPTIONS only.

Default quotas are 20 requests per IP/hour, 200 requests per school/hour and 3 new submissions per recipient/day, configurable in settings. PostgreSQL row locks and unique buckets enforce these across workers; they do not rely on process-local DRF cache throttles. Database failure fails closed. Only explicitly configured trusted proxy CIDRs permit right-to-left forwarded-IP extraction. Untrusted forwarding headers are ignored. Verify hosting proxy networks and TLS-header trust before deployment; use edge protection as an additional layer.

Turnstile verification uses the fixed HTTPS Siteverify endpoint, bounded responses, timeout, expected hostname and beavers_intake action. Verification retries are namespaced by tenant, endpoint kind and submission UUID. No provider error text or secret is returned to clients. Missing/failed verification is not accepted. Reference: https://developers.cloudflare.com/turnstile/get-started/server-side-validation/ . The public widget/site key belongs to the later website phase; only the secret is configured here.

Beavers origins are allowed through a route-scoped django-cors-headers signal only on the two public POST/OPTIONS endpoints. They are not added to the global staff API origin allowlist. Idempotency-Key is permitted in CORS preflight. Existing private origins/JWT permissions remain unchanged.

General logs/audits do not contain submission bodies, notes, names, DOBs, authentication tokens or SMTP/provider errors. Private notes are stored only in scoped histories. No frontend or offline IndexedDB changes were made; intake responses must remain excluded from offline caching when the dashboard is implemented.

## Email and retention commands

A saved submission creates two durable jobs: the fixed school notification recipient beaversecdcentre@gmail.com and the validated visitor/guardian email. No SMTP calls occur in submission transactions. Templates contain a reference and generic acknowledgement only, not pupil DOB/name or submitted message text. The worker is disabled unless both delivery-enabled and SMTP-verified flags are set and the existing MAILERS configuration has SMTP, host, credentials, TLS and a valid sender.

After configuration, schedule: python manage.py process_intake_email --limit 100. Claims use SKIP LOCKED on the outbox row itself, unique lease tokens and timeouts; delivery happens outside DB transactions. Failures are retryable with capped backoff and safe codes. Record storage is never rolled back because SMTP fails. A crash after provider acceptance can cause a retry: delivery is at-least-once, not guaranteed exactly-once; Message-ID is stable per job. Monitor exhausted attempts and configure provider deliverability/verified sender separately.

Expired records are not eligible for new email claims. python manage.py purge_intake_records is a dry-run count report; --execute deletes expired records, their private histories/outbox jobs, related/expired submission keys and expired rate buckets, retaining metadata-only audit records and logging purge events. Schedule this only after retention/deletion policy approval. Backups require their own approved expiry policy.

## Files changed

Existing: backend/core/models.py (register new models only), core/urls.py, core/apps.py, config/settings.py, and README.md.

New: core/intake_models.py, intake_serializers.py, intake_security.py, intake_services.py, intake_api.py, intake_email.py, intake_cors.py, core/test_intake.py, core/management/commands/process_intake_email.py, purge_intake_records.py, core/migrations/0022_intake_admissions_enquiries.py, backend/.env.intake.example and this report.

No existing Student/Parent/Enrollment implementation, authentication/permission classes, MTM frontend, Beavers website or MDS website was changed. A pre-existing modification to docs/FOCUSED_ATTENDANCE_SUBJECT_FINANCE_REPORT.md was left untouched.

## Validation

185 core tests passed, including 30 new intake tests and the existing 155 tests. Tests ran against a separate disposable local PostgreSQL cluster on loopback port 55482; the Django test database was created/migrated/destroyed there. No production schema or tenant data was touched. Full regression used a temporary test-only fast password hasher and per-case cache isolation; production hashers and throttle settings were unchanged. The initial 20 intake tests also passed with the normal configured hashing.

Coverage includes valid submissions, required/invalid/unknown fields, forged ownership, consent, UUID keys, identical/conflicting replays, public methods/size limits, production gates, suspended/demo/archived schools, JWT revocation/roles/password-change policy, cross-school access/assignment, concurrent review conflict, concurrent duplicate saves, shared quota concurrency, atomic rollback, safe audit/history, CORS isolation, trusted proxies, challenge hostname/action/provider failure, disabled email, retryable SMTP failure/success, concurrent email claims and dry-run/executed retention cleanup. All email and challenge provider calls in tests were mocked; no real emails were sent.

Django system checks, migration drift check (makemigrations --check --dry-run) and git diff --check passed. No migrations were applied to the regular development or production database. The missing local staticfiles directory generated a test warning; it is unrelated to intake and no deployment/static-file changes were made.

## Configuration still required

See backend/.env.intake.example. Required to enable collection: MTM_INTAKE_ENABLED, confirmed MTM_INTAKE_BEAVERS_SCHOOL_ID, MTM_INTAKE_PRIVACY_APPROVED, MTM_INTAKE_PRIVACY_VERSION, the independent key retention-day value and MTM_INTAKE_ALLOWED_ORIGINS. Production also requires MTM_INTAKE_CHALLENGE_REQUIRED=true and MTM_INTAKE_CHALLENGE_SECRET, verified HTTPS/proxy boundaries and PostgreSQL. Configure trusted proxy CIDRs to the verified hosting network, not arbitrary broad public ranges.

Email requires MTM_INTAKE_EMAIL_ENABLED and MTM_INTAKE_SMTP_VERIFIED plus existing DJANGO_EMAIL_BACKEND, EMAIL_HOST/PORT/HOST_USER/HOST_PASSWORD/USE_TLS and DEFAULT_FROM_EMAIL. Optional controls: MTM_INTAKE_MAX_BYTES, IP/SCHOOL/RECIPIENT_LIMIT, EMAIL_MAX_ATTEMPTS and EMAIL_LEASE_SECONDS. The fixed school notification recipient is not client-controlled.

The migration exists but is unapplied outside tests. The real Beavers tenant ID, approved policy/retention values, allowed production origins, challenge keys/widget, verified SMTP sender and worker/purge schedules are still required. Public submissions and real email delivery are not operational until these are reviewed and configured. Connecting the Beavers forms, adding MTM dashboard pages and future approved enrolment are outside Phase 1 and were not implemented. No production configuration was invented or activated.

## Corrected school retention lifecycle

Pending and approved applications, and new/in-progress enquiries, have NULL retention expiry. Rejection or resolution starts one calendar month in Africa/Harare, clamped at month end. Reopening clears expiry; notes, assignments and repeated terminal status do not extend it. Legacy application/enquiry RETENTION_DAYS settings are ignored. Technical key expiry remains independently day-based.

Cleanup only deletes expired rejected/resolved records without retention_hold. Approved applications are always preserved: there is no verified transfer/recordkeeping workflow yet. Set preservation holds through an authorized internal database process before cleanup where required; the public and review APIs cannot alter holds. Cleanup serializes with review using school locks; private history/outbox rows cascade only on eligible deletion, while metadata audit entries remain.

Production requires migration 0023 (and 0022 if not already applied). Pause purge workers during the code/schema rollout. Migration 0023 is intentionally irreversible and repairs expiry from the latest genuine terminal transition history; records without evidence remain unexpired for manual review. Review a dry-run before any executed purge because historical terminal deadlines may already have passed. No production migrations or deployment were performed. MTM_INTAKE_ENABLED remains false by default and in the example configuration.
