# Provisioning a real school

Run `provision_school` only after the operator confirms the real details and the
target database. Back up that database before the first live write. Keep the
backup and input in restricted storage, outside Git. `.local-provisioning/` under
`backend/` is ignored for local input; it is not a substitute for access controls.
Do not run the demo commands against a pilot database.

From `backend/`, the commands for the confirmed Beavers input will be:

```powershell
.\venv\Scripts\python.exe manage.py provision_school --input .local-provisioning\beavers-junior-school.json --dry-run
.\venv\Scripts\python.exe manage.py provision_school --input .local-provisioning\beavers-junior-school.json
```

Each execution requests the password twice through a hidden terminal prompt.
Alternatively supply `MTM_PROVISION_ADMIN_PASSWORD` in the process environment
through a secure local mechanism. Never put passwords in JSON, command arguments,
source control, chat, or logs. The command removes the variable from its own
process; the operator must remove it from any parent shell as well. Both modes
validate Django's configured password policy. There is no password CLI flag.

## Input contract

JSON contains exactly these five keys; unknown fields (including `school_id`,
roles, privilege flags, and passwords) are rejected. All scalar inputs are strings.

| Object | Required fields | Optional fields |
| --- | --- | --- |
| `school` | `name`, `email`, `phone_number`, `default_currency` | `address` |
| `administrator` | `username`, `email`, `first_name` | `last_name` |
| `academic_year` | `name`, `start_date`, `end_date` | None |
| Each item in `terms` | `name`, `start_date`, `end_date` | None |
| Each item in `classes` | `name` | None |

`terms` and `classes` must be nonempty lists of objects. Dates use `YYYY-MM-DD`.
Terms must be supplied in chronological order; sequence numbers start at one.
Dates must fall inside the year, must not overlap, and each end must follow its
start. The year is marked current. The currency must be a confirmed uppercase
three-letter code; the models have no currency registry to validate membership.
Confirm the administrator's complete name and its first/last-name split; a
single-name administrator can omit `last_name`.

The models have no school slug/code, per-school time zone, or separate grades.
The application time zone is UTC. Confirm the grades offered and actual class
names so the existing `SchoolClass` rows reflect the real structure. No grade
rows or inferred classes are created. If separate grades or local school time
zones are needed, that requires a separately agreed model change.

No communication settings are required to provision. This command leaves them
uncreated; the existing communication service defaults WhatsApp to disabled.
It creates no students, parents, attendance, results, payments, fees, balances,
notifications, or subjects.

## Validation and atomicity

Dry run validates unsaved model instances and passwords without INSERT/UPDATE/
DELETE statements. Live execution validates again and uses one transaction for
the existing provisioning service, academic records and audit events. Audit actor
is null because execution is by an operator command, not the new administrator.
Success reports identifiers only, after commit. A new account is active, has the
school administrator role, no staff/superuser privileges, and must change its
password before school APIs allow access.

Duplicate name/email checks include every school, even archived/demo schools.
Username/email checks include every user, even inactive users. Comparisons ignore
case and surrounding/repeated whitespace. Existing accounts are never reused.
Database constraints additionally protect exact unique school names/emails and
usernames. **Existing schema does not enforce case-insensitive uniqueness or
unique user email.** Run provisioning as a single operator operation, without
concurrent school/user creation through other entry points; those other paths
do not share all of this command's stricter checks.

## Pilot execution gate

1. Confirm all real values, target database/deployment and a secure password
   delivery method. Do not invent missing dates or classes.
2. Take a database-native backup (PostgreSQL: `pg_dump` custom-format archive),
   record its location and checksum, and verify it can be read/restored in an
   isolated environment. Never print connection strings or credentials.
3. Run dry run and show its result. If it succeeds, run live provisioning.
4. Verify authentication without displaying JWTs. The administrator must complete
   the password-change flow. Verify own-tenant reads and foreign-tenant denied
   reads/writes; any live mutation probe must run in a rollback-only transaction.
   Do not create test learners or parents in the live database.
5. Report identifiers and stop before importing children or parents.

Automated tests use a separate Django test database. Never point a test database
name at the pilot database. The checked environment uses PostgreSQL; SQLite can
be used for isolated local regression tests but does not validate PostgreSQL
concurrency semantics. Review `check --deploy` before public exposure: development
settings are not a production security configuration.

## Validation recorded for this change

- All 10 provisioning tests passed in isolated SQLite with the configured PBKDF2
  hasher and normal authentication settings.
- All 116 backend tests passed in a uniquely named disposable PostgreSQL test
  database. That broader run used a fast test-only password hasher and DummyCache
  to avoid shared login-throttle state between existing tests. Neither override
  was written to application settings. The test database was destroyed afterward.
- `manage.py check`, `makemigrations --check --dry-run`, and `git diff --check`
  passed. No schema migration is needed.
- The SQLite broader run has an existing decimal-formatting failure in fee
  reminders (`75` versus `75.00`); this test passes on PostgreSQL.
- `check --deploy` reports console-only email, DEBUG enabled, no HTTPS redirect,
  insecure session/CSRF cookies, and no HSTS in the current environment. These
  remain deployment configuration issues to resolve before public pilot use.
- No cross-school access was found in the tested APIs. This is test coverage,
  not a claim of a comprehensive security audit.
