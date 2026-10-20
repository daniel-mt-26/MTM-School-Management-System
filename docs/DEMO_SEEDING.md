# Sunrise demo seeding and walkthrough

The complete fixture set is synthetic. No real learners, contact addresses,
bank records or security events are imported. All email addresses use `.invalid`.
The commands do not contact mail, WhatsApp, password-recovery or payment providers.

## Prerequisites and commands

Run the commands from `backend/`. Use an environment with its normal dependencies, including ReportLab, and
the existing schema through `0030_school_financial_management`. These commands
never apply migrations. Do not point an unmigrated application at the new features.
The implementation adds no migration and uses the existing `School.is_demo` flag.

Create the controlled Sunrise tenant and seed it:

```powershell
python manage.py create_demo_school
```

Seed an existing, explicitly marked demo school (confirmation is mandatory):

```powershell
python manage.py seed_demo_school --school "Sunrise Primary School" --yes
python manage.py seed_demo_school --school "Sunrise Primary School" --yes --as-of 2026-10-20
python manage.py verify_demo_school --school "Sunrise Primary School"
```

Repeat either seed command without duplicating rows or changing existing passwords.
The first run stores its calendar; later runs reuse that exact date. To deliberately
move the calendar, reset with an explicit new `--as-of` date. The default calendar
is the Django local date at first seed. The October example makes all three terms
and the previous year visible during a walkthrough.

```powershell
python manage.py seed_demo_school --school "Sunrise Primary School" --reset-first --yes
python manage.py seed_demo_school --school "Sunrise Primary School" --reset-first --yes --as-of 2026-11-20
python manage.py reset_demo_school --school "Sunrise Primary School" --yes
```

The existing `create_demo_school --reset --yes` spelling delegates to the same
reset implementation. `reset_demo_school` requires an existing marked school;
it never creates one or converts a customer school into a demo school.

## Safety, ownership and repeatability

The seed command requires an existing school, `is_demo=True`, and `--yes`.
The controlled create command accepts only the Sunrise name and reserved email;
a live school owning either identifier causes refusal. Other marked demo tenants
can be seeded explicitly, using their own username namespace.

One database transaction locks the selected School row, checks the manifest,
creates the fixtures and runs integrity verification. Concurrent seed/reset
commands for that school serialize. Any error rolls back the database work.

The existing `IdempotencyRecord` table stores a versioned management-command replay
record (`request_method=COMMAND`, `/management/seed_demo_school/v1/`). Its JSON body
contains the pinned calendar and exact model/primary-key ownership manifest. It
contains no passwords, tokens or connection credentials. This management namespace
is separate from HTTP mutation keys. Do not delete this record as cache cleanup:
it is the provenance required to reset safely.

Rows reused from existing configuration are explicitly recorded as unowned.
Reset deletes only rows the manifest proves were created by this seeder. It
preserves the School, administrator account, existing branding/configuration,
invoice sequence, platform users, other schools and unowned records. It checks
incoming foreign-key and many-to-many dependencies before deletion, including
relations that would otherwise cascade or become null. An operator-created row
depending on a generated row blocks reset; it is never silently deleted.

Missing, moved or foreign manifest records also cause refusal, rather than
guessing ownership from a `Demo` prefix. Older 24-learner fixtures from the former
command have no manifest and are retained as unowned data; they are not silently
purged. On an upgraded pre-populated tenant the managed counts describe the new
fixture set; overall school counts may also include those older records.

Generated PDF resource/supporting fixtures use actual private storage files.
Database failures clean up newly written files; successful reset schedules old
fixture cleanup only after commit. Storage deletion is best effort, so a storage
outage can leave an unused file for operator cleanup, never a fabricated reference.
No existing logo or file is replaced. Invoice numbers continue the genuine
school-local sequence after reset; old official numbers are not reused. Database
primary keys and generated passwords change after reset; scenario values remain
deterministic for the same calendar.
Reload the demo online after reset. Browser caches and queued offline mutations
are outside the command's ownership; do not replay old demo work against rebuilt IDs.

## Accounts and credentials

Sunrise usernames:

| Role | Username |
| --- | --- |
| School administrator | `sunrise-admin` |
| Teachers | `sunrise-teacher-01` through `sunrise-teacher-05` |
| Walkthrough parent, two children in different classes | `demo.parent` |
| Other guardians | `sunrise-parent-02` through `sunrise-parent-31` |

New accounts receive secure random temporary passwords, shown once after a
successful seed. They require password change on first sign-in, just like normal
accounts. Password hashes, JWTs and recovery tokens are never printed or seeded.
Existing credentials and live session settings remain unchanged on ordinary reruns.
Demo-generated teacher/parent accounts are replaced during reset, invalidating old
account references; the bootstrap administrator is preserved.

For reproducible private walkthrough credentials, configure these environment
variables locally before creation, rather than putting passwords into source or
shell command history:

```text
MTM_DEMO_ADMIN_PASSWORD
MTM_DEMO_TEACHER_PASSWORD
MTM_DEMO_PARENT_PASSWORD
```

Configured passwords are not echoed. They are used only for newly created demo
accounts, not to reset an existing user's password. Existing admin-assisted reset
and first-login password-change flows remain available. No platform administrator
credential is created or modified. The command reports all newly generated
credentials, plus the main walkthrough usernames and managed record counts.

## Managed data and intentional scenarios

| Area | Fixtures |
| --- | --- |
| School | Fictional Harare address, reserved phone/email, USD; motto, website, parent-invoice access and A-D grade scale when settings are absent. Existing settings and logos are preserved. |
| Academic context | Previous/current calendar year, three four-month demonstration terms per year, Grades 2-7, ten learners per class, six subjects. Dates are demonstrative rather than an official Zimbabwe term calendar. |
| Teachers | Five active accounts, 30 teacher/class assignments covering both years; multiple classes and subjects per teacher. |
| Learners | 60 named synthetic learners with DOB, reserved admission numbers, two enrollments and guardian/finance links. |
| Guardians | 31 accounts; `demo.parent` has two children in different classes; the first learner has two guardians; one guardian has no email. |
| Timetables | Current-term class plans across Monday-Friday, assigned subjects and labelled breaks; grade slots are staggered to avoid shared-teacher conflicts. |
| Attendance | Weekdays across the 90-day window ending on the pinned date, with P/A/L/E patterns for every class. No future attendance. |
| Homework | Draft, Published and Closed items for every class; published/closed work is parent-visible through existing permissions. |
| Announcements | Admin to all/selected/one teacher; an assigned teacher to all/selected/one assigned class; corresponding in-app notifications and a school announcement. |
| Results/comments | Six subjects per learner, previous-year history and elapsed current-year terms; current-term Draft/Submitted/Approved/Published examples; teacher comments and official publication snapshots. Future terms remain empty. |
| Financial structures | Tuition TERMLY; Transport, After School Care and Meals MONTHLY; Development Levy and Stationery ONE_OFF. Tuition, transport and development examples have linked charges. |
| Student finance | Fully paid, partial, unpaid, multiple-charge and tuition-paid/transport-outstanding learners; previous-year carried balance and a new not-yet-due charge. |
| Ageing | Real due dates at 10, 45, 75 and 120 days before the pinned date, plus a future due date. Existing report code calculates the buckets. |
| Payments/receipts | Canonical payment service, exact linked ledger entries/receipts, cash/bank/mobile-money examples, original dated transactions and payment classification. Notifications are explicitly suppressed for seed payments. |
| Invoices | Official service-generated invoices covering paid, part-paid and unpaid tuition, plus separate transport/development invoices for two multi-charge learners; school-local numbering and immutable branding/charge snapshots. |
| Statements | Derived from actual dated obligations/payments, including a previous-year opening balance; linked parents can view their own children. |
| School finance | Nine manual non-student income records, 30 expenses across ten configured categories, two cash/bank accounts, monthly notes and safe expense PDF. |
| Reporting | Income, Cash Book, Cash Received, monthly/annual reports and dashboard aggregate the canonical transactions. No totals or duplicate cashbook rows are seeded. |
| Inventory | Five categories, seven items, two variants per item, opening adjustments, receipts and issues, with positive stock. |
| Resources | Three generated, explicitly synthetic revision PDFs with authorized class/subject/teacher links; no broken file paths. |
| Audit | Explicit `demo_seed_*` action events plus genuine invoice/publication events; no fabricated failed logins, consent or security events. |

The current Student model has no gender field and no automatic admission-number
allocator. This seeder reserves `DEMO-YYYY-NNNN` within the school's existing
admission uniqueness rule; it does not invent a second production allocator.

Overpayments are rejected by the canonical payment service. Negative credit
adjustments also fail the current model's minimum-amount validator, so this seeder
does not bypass validation to fabricate a credit-balance learner. The existing
invoice model supports one assignment/line per invoice. Multiple charge types are
demonstrated on statements and separate official invoices, not an unsupported
multi-line invoice. Report cards contain structured data/publications, not an
invented future report-card visual template or a nonexistent uploaded report file.
The existing Outstanding Balances/Ageing API intentionally returns positive
debtors only. Fully paid learners are present in the dataset and can be shown in
Student Balances and statements; the seeder does not change that report filter.
Bank reconciliation, budgets and future staff features remain outside scope.

## Verification and tests

`verify_demo_school` is read-only and exits nonzero for serious integrity errors.
It checks manifest existence/ownership, tenant-bearing references, teacher subject
authorization, guardian/enrollment/finance coverage, attendance and result states,
actual fixture files, receipt/ledger linkage, invoice totals, statement balances,
all ageing buckets, unique cashbook source IDs, monthly/annual reconciliation,
positive inventory and audit coverage. It also runs inside the seed transaction.

Backend checks:

```powershell
python manage.py test core.test_demo_seed --settings=config.test_settings --noinput --keepdb
python manage.py test --settings=config.test_settings --noinput --keepdb
python manage.py check
python manage.py makemigrations --check --dry-run
git diff --check
```

Tests use temporary local file storage and the isolated PostgreSQL test database.
No application database is seeded by running tests. No frontend fixture or source
change is needed for the management-command implementation.

## Demo walkthrough order

1. Admin Dashboard: log in and change the temporary password.
2. Teachers: assignments, account state and teacher login.
3. Students/Parents: two children under `demo.parent`, two guardians for the first learner.
4. Timetable: class and teacher personal views.
5. Attendance: pinned current/previous months and Monthly Register exports.
6. Homework: Draft, Published and Closed.
7. Announcements: staff and assigned-class recipients.
8. Results: teacher drafts, admin review and published records/comments.
9. Parent Portal: linked children, published results, homework and historical records.
10. Fee Structures: termly/monthly/one-off definitions.
11. Charges: select a learner with several charge types.
12. Payments/Receipts: full/partial settlement and protected receipt PDF.
13. Invoices: paid, part-paid and unpaid documents.
14. Statements: previous-year opening balance and dated running balance.
15. Outstanding Balances: varied debts; use Student Balances/statements for zero balances.
16. Ageing Debtors: use the pinned reporting date for all five buckets.
17. Expenses: categories, suppliers and the synthetic supporting PDF.
18. Cash Book: real money in/out and running balances.
19. Cash Received: receipt references and method totals.
20. Monthly Financial Report: choose the pinned month.
21. Annual Financial Report: compare the monthly breakdown.
22. Financial Dashboard: billed, collected, other income, expenses and receivables.
23. Inventory: variants, stock receipts/issues and current quantities.
24. Audit Log: clearly labelled synthetic actions.
