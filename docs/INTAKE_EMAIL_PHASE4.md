# Beavers intake email: Phase 4

The existing durable PostgreSQL outbox and finite delivery command are reused. No second email system, Celery, Redis, frontend changes, new authentication or enrolment workflow was introduced. No Beavers/MDS website, school administrator permission or student/parent functionality was changed. No real emails, deployment, GitHub push, production migration or billable Render service creation was performed.

## Inspection and implementation

Phase 1 and Phase 3 reports, outbox model/constraints, submission/review services, email code/command, settings, installed Django mailer source and Render blueprint were inspected. Public submissions already create two outbox jobs transactionally. Idempotent replays reuse the same application/enquiry and do not create jobs. Database uniqueness prevents duplicate purposes per saved record. Those mechanisms and the public queued response contract are unchanged.

Inspection found that the former `get_connection(backend=...)` call is incompatible with the repository's Django 6.1 `MAILERS` configuration. Delivery now uses `mailers.default.send_messages([message])`, and tests exercise the real mailer construction while mocking its transport. See Django's [MAILERS migration documentation](https://docs.djangoproject.com/en/dev/howto/mailers-migration/).

## Files changed

Existing files modified:

- `backend/core/intake_email.py`: four template messages, safe Django mailer call, tenant/configuration gates, temporary/permanent failures, retry/lease recovery and attempt audit metadata.
- `backend/core/management/commands/process_intake_email.py`: existing batch command plus optional scheduler failure flags.
- `backend/config/settings.py`: SSL, timeout, server-controlled recipient, dashboard origin and contact configuration.
- `backend/.env.intake.example`: server-only SMTP/content settings with activation flags disabled.
- `backend/core/test_intake.py`: existing delivery mocks updated to the supported mailer API and scoped lease fixtures.

New files:

- `backend/core/test_intake_email.py`: 19 email tests with synthetic data and mocked SMTP only.
- Eight templates under `backend/core/templates/intake/`: `application_school`, `application_ack`, `enquiry_school`, `enquiry_ack`, each with a `.txt` body and `.subject.txt` subject.
- `docs/render-intake-email-cron.example.yaml`: opt-in scheduler example, not an active deployment blueprint.
- `docs/INTAKE_EMAIL_PHASE4.md`: this report and setup guide.

No model change or new migration is needed. The existing Phase 1 migration must still be released through the normal deployment process. `render.yaml`, both frontends and backend submission/permission endpoints are untouched.

## Messages

| Message | Subject | Body content |
| --- | --- | --- |
| School admission notification | New Admission Application – Beavers Junior School | Reference, requested grade, server submission date in Africa/Harare, authenticated admissions detail link. |
| Parent acknowledgement | Admission Application Received – Beavers Junior School | School name, reference, receipt, recorded as pending review at submission, no guarantee of admission, school email/telephone contacts. |
| School enquiry notification | New Website Enquiry – Beavers Junior School | Reference, submission date and authenticated enquiry detail link. |
| Visitor acknowledgement | Enquiry Received – Beavers Junior School | Reference, receipt, response through supplied contact information and school contacts; no promised timeframe. |

The school notification destination defaults to the confirmed `beaversecdcentre@gmail.com`, separate from the provider-authorised sender. The confirmed telephone contacts are `+263 775 177 935` and `+263 772 405 912`. Templates receive a strict minimal context, never the record object, names, birth date, residential address, full enquiry message, visitor subject, credentials or review notes. No sensitive attachments are included. Dashboard links contain a UUID and no authentication token; existing login/role/school restrictions apply. Reply-To uses the school contact email, not the visitor address.

Acknowledgements describe the submission receipt, not a later admission decision. This remains accurate if an administrator reviews an application before its acknowledgement is processed.

## Outbox reliability and failure states

Each send is claimed with PostgreSQL `SKIP LOCKED`, a unique lease token, an actual incremented processing-attempt counter and bounded socket timeout. The configured lease must cover at least ten socket-timeout intervals; defaults are 600 seconds and 15 seconds. Only the configured active, non-demo Beavers tenant's jobs are processed. Retention-expired records are not delivered. Recipients must be valid and match the saved visitor email or currently approved school destination; queued recipient changes require operator review.

Transient SMTP 4xx, disconnections/timeouts and unconfirmed send results become retryable failures. Backoff is 2, 4, 8, 16, 32 minutes for the default five attempts, capped at one hour for larger limits; the scheduler may deliver later than that due time. Permanent SMTP 5xx recipient/data failures, invalid/mismatched recipients and malformed messages stop automatic retry. Permanent sender/authentication, unsupported security or certificate errors stop the batch to avoid exhausting other jobs. Temporary 4xx authentication failures remain retryable. Exhausted attempts stop retries without inflating the actual count. A stale crashed final lease becomes `delivery_uncertain`, requiring review instead of an automatic extra send.

Outbox rows retain status, attempt count, last safe failure code, scheduling/lease timestamps and SMTP acceptance time. Existing append-only AuditLog records each completed attempt's job UUID, purpose, attempt number and safe outcome code only. Neither provider exception text nor bodies/recipients/SMTP credentials are logged. Successful submissions are independent of SMTP processing and are never rolled back because delivery fails.

The existing stable Message-ID is retained on retries. Submission idempotency does not resend sent acknowledgements. SMTP itself cannot atomically commit with PostgreSQL: a process killed after provider acceptance but before marking the job sent can cause duplicate delivery on recovery. Stable Message-ID is not guaranteed provider deduplication. This remains an at-least-once delivery system, not an exactly-once inbox guarantee. `sent` means accepted by SMTP, not confirmed inbox delivery; asynchronous bounces/spam placement are not confirmed by this worker. The website's queued/saved wording is unchanged.

Safe terminal codes are `smtp_permanent`, `smtp_configuration`, `recipient_invalid`, `recipient_mismatch`, `message_invalid`, `retention_expired` and `delivery_uncertain`. Retryable codes are `smtp_temporary` and `provider_error`. Monitor failed/exhausted jobs privately. Correct provider/recipient configuration and investigate uncertain sends before manually resetting a specific job; there is no bulk automatic replay of terminal failures. Do not reset counters or replay all jobs blindly.

## Required SMTP and content settings

All are backend/worker environment variables, never `VITE_*` or browser values:

| Variable | Required configuration |
| --- | --- |
| `DJANGO_EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` for live intake delivery. |
| `EMAIL_HOST`, `EMAIL_PORT` | Actual provider-approved hostname/port; none was guessed. |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | Provider-issued credentials stored securely in Render, never committed. |
| `EMAIL_USE_TLS`, `EMAIL_USE_SSL` | Exactly one enabled: commonly STARTTLS on 587 or implicit TLS on 465, according to the provider. |
| `EMAIL_TIMEOUT` | Finite socket timeout, default 15 seconds; readiness accepts 1–30 seconds. |
| `DEFAULT_FROM_EMAIL` | Provider-authorised sender address. Gmail notification ownership does not establish sender authorisation. |
| `MTM_INTAKE_SCHOOL_EMAIL` | School notification destination, default `beaversecdcentre@gmail.com`. |
| `MTM_INTAKE_DASHBOARD_URL` | Approved HTTPS MTM frontend origin only, e.g. the real dashboard host; no `/login`, `/api`, credentials, query or fragment. Blank by default pending confirmation. |
| `MTM_INTAKE_CONTACT_EMAIL`, `MTM_INTAKE_CONTACT_PHONES` | Confirmed school contacts included in acknowledgements; approved defaults above. |
| `MTM_INTAKE_BEAVERS_SCHOOL_ID` | Actual existing Beavers database PK, not registration number 8742. |
| `MTM_INTAKE_EMAIL_ENABLED`, `MTM_INTAKE_SMTP_VERIFIED` | Both `true` only after provider/sender approval and an explicitly approved real-delivery smoke test. Defaults remain false. |
| `MTM_INTAKE_EMAIL_MAX_ATTEMPTS`, `MTM_INTAKE_EMAIL_LEASE_SECONDS` | Default 5 and 600; review with timeout and operational needs. |

SMTP provider, credentials, authorised sender, exact dashboard origin and production tenant/service configuration were not provided or activated. Do not assume a school Gmail mailbox can be used as SMTP sender. Configure SPF/DKIM/DMARC as required by the chosen provider and approved sending domain. TLS settings follow Django's [email backend configuration](https://docs.djangoproject.com/en/6.0/topics/email/).

## Render scheduler: exact recommended setup

The repository's `render.yaml` defines one API web service, `mtm-sms-api`, and no intake scheduler. The actual Render account, deployed service name, region, plan and SMTP provider were not accessible/verified. A separate **paid cron job** is recommended; PostgreSQL remains the queue, so Redis/Celery or a continuous worker is unnecessary.

After release/configuration approval, in Render select New > Cron Job, connect the same MTM repository/released branch, choose Python, root directory `backend`, and select the verified API/database region. Use plan `0.5c-512mb`, build command `pip install -r requirements.txt`, UTC schedule `*/5 * * * *`, and this finite start command:

```sh
python manage.py process_intake_email --limit 100 --require-enabled --fail-on-error
```

Keep auto deploy off. The accompanying example shows environment references to the API service; verify its actual name and ensure every referenced key is defined before using it. Supply the same approved Django secret, PostgreSQL connection, existing production host/CORS/CSRF/security and required Supabase media settings, plus SMTP/intake settings above. These existing settings are required to initialise this Django project even though this command sends no media. An approved Render environment group can share them instead. Never generate a new database or copy guessed credentials.

The example intentionally leaves email-enabled and SMTP-verified false. Change them only after approval in the reviewed worker configuration; `--require-enabled` will otherwise fail safely without spending job attempts. `--fail-on-error` marks runs failed when this batch records delivery problems, allowing Render failure notifications while retryable jobs stay scheduled. Review private failed/exhausted jobs and queue age separately; a later run with no eligible work does not resolve terminal failures.

Render schedules use UTC, supports shared environment groups and permits only one run of a cron service at a time. Manual Trigger Run cancels an active run, so avoid triggering it while sending; cancellations use lease recovery and may have uncertain SMTP outcomes. See [Render cron setup](https://render.com/docs/cronjobs) and [Blueprint reference](https://render.com/docs/blueprint-spec). Verify SMTP connectivity from the selected paid runtime: [free Render web services block SMTP ports 25, 465 and 587](https://render.com/docs/free).

## Expected additional hosting cost

Prices checked on 13 October 2026, in USD. Render's smallest cron compute rate is $0.00016/minute with a $1/month minimum per cron service. A five-minute schedule has 8,640 runs in a 30-day month: assumed 10-second runs total 1,440 minutes ($0.2304 compute, billed at the $1 minimum); assumed 60-second runs total 8,640 minutes (about $1.38). These are runtime-based estimates, not guaranteed bills. SMTP volume/startup/retries can increase runtime. Existing API/database, workspace, SMTP-provider and other usage charges are additional. A continuously running smallest background worker is listed at $7/month, but is not needed for this recommended finite-command cron setup. Sources: [Render pricing](https://render.com/pricing), [cron billing/minimum](https://render.com/docs/cronjobs). No service or charge was created.

## Tests and activation status

All 49 targeted intake/email tests passed, followed by all 204 core backend tests (185 existing and 19 new email tests). Tests ran against a disposable Django test database inside the isolated PostgreSQL cluster on loopback port 55482, with temporary test-only fast hashing/cache isolation; normal development and production schemas/data were untouched. Django system checks, `makemigrations --check --dry-run` and `git diff --check` passed. No new migration is needed. Tests cover all four templates/recipients, strict data minimisation, real Django mailer construction, atomic queuing, idempotent retries, SMTP temporary/permanent failures, backoff/exhaustion, stable Message-ID, leases/uncertain recovery, tenant scope, safe audit metadata, sender/TLS/configuration gates and command execution/error exits. All provider sends are mocked; no real emails are sent.

Implementation is ready for configuration and an explicitly approved staging smoke test. It is **not ready for production activation** without confirmed provider/sender credentials, dashboard origin, real tenant binding, released Phase 1 migration, an approved paid scheduler and delivery monitoring. Collection privacy/retention/Turnstile gates from earlier phases remain separate and unchanged. Permission rules and automatic enrolment behaviour are unchanged.
