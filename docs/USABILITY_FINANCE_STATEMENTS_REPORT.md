# MTM SMS usability and account statements ? final implementation report

Implemented in the working tree on 6 October 2026. No deployment, commit, or push was performed. Application data was not migrated or rewritten during this run; database verification used an isolated PostgreSQL test database.

## 1. Attendance button root cause

The existing click handler already changed `roster.students[].attendance.status` and marked that row `changed`. Two problems made the workflow unreliable: `aria-pressed` had no selected-state CSS, and asynchronous roster refreshes replaced the entire roster, including unsaved edits. The latter was a real state-loss path when connectivity/sync revision changed while a teacher was marking attendance.

Refreshes now merge changed rows only within the same class/year/term/date context. The original `updated_at` is retained so server conflict detection still works. Starting a save invalidates an older roster request. Explicit ?Use server value? bypasses draft preservation. Selected status has a strong background, border, and pressed state; keyboard focus remains visible.

Present, Absent, Late, and Excused remain available. Mark All Present changes local rows only. Save explicitly submits the selected values. Tests exercise every status, background refresh, online bulk payload, offline queue payload, and remount/restoration of a queued exception.

## 2. Attendance history

Current Attendance and Attendance History are available from the same page. History supports year, term, class, date range, name/admission search, and a student-specific history opened by clicking a student. It shows historical class membership from the recorded enrollment and counts for all four statuses. It does not infer historical class from the student's current class, and does not change AttendanceRecord rows.

`GET /api/school/attendance/history/` scopes both records and related enrollments to the authenticated school. Invalid dates are rejected; foreign year/term filters return 404.

## 3. Timetable year/term loading root cause

The previous page assigned all six lookup/list responses only after one `Promise.all` completed. Failure of the timetable list, subject library, or any other request left otherwise successful year/term responses unused. The page now loads and retains each successful response independently and identifies failed resources. A regression test injects a failing timetable-list request and verifies that years and dependent terms remain selectable.

Historical years are included. Changing year clears term; the term dropdown filters by year. Empty lists have explanatory messages. This establishes and repairs the frontend failure path; it does not claim a particular failing live request was captured from the user's browser.

## 4. Timetable scope

Timetable has an explicit SINGLE, MULTIPLE, or WHOLE_SCHOOL scope. SINGLE requires one class; MULTIPLE retains the checklist; WHOLE_SCHOOL resolves all active classes in the authenticated school dynamically, while the timetable's year and term determine its schedule context. Whole-school applicability is not stored as a snapshot of class IDs. New active classes are included in list queries, parent timetable queries, and conflict checks.

Existing class/year/term authorization and half-open time overlap rules remain. Tests cover overlaps in both directions between whole-school and class-specific schedules, including a class created after the whole-school timetable.

## 5?6. Subject workflow

The timetable's Curriculum Setup link was removed and the old curriculum route redirects to Academics. The unused old component remains in the source for compatibility, but is not a routed workflow.

A shared searchable, grouped SubjectPicker exposes the Zimbabwe library directly in Timetables, Homework, and Results. Selecting a built-in subject uses the existing idempotent subject-materialization endpoint (its compatible API name remains `subjects/activate`) without a separate activation screen. Existing school subjects are reused. Other / Custom Subject creates a normal school-owned Subject.

Results reuse or create the appropriate ClassSubject for the chosen enrollment's class and year. Report cards continue to derive subjects from those results; no separate report-card curriculum setup is needed. Timetable activities remain a separate selector. Existing Subject, ClassSubject, result, homework, and timetable references are preserved.

## 7. Fee validation findings

The old UI flattened error-object values into one banner, discarding field names and producing repeated ?This field is required? text. The current backend already made the formerly hidden legacy `start_month` and `currency` fields optional for managed fees, deriving them from term and school. Tests of the current backend confirm that complete visible-field payloads work for MONTHLY, TERMLY, and ONE_OFF; the reported complete-form rejection was not reproduced against this backend revision.

The form now sends an explicit allowlist of editable fields, clears class/student values when scope changes, and displays returned errors beside their fields. Unrecognized field errors retain their field names. The serializer now identifies a year/term mismatch specifically on `term`. Tests assert the actual payload, optional hidden fields, and two separate required-field messages without a duplicate generic banner.

One-off retains year and term: existing financial obligations, enrollment eligibility, generation identity, and historical reporting require that context. No schema was relaxed to manufacture context-free obligations.

## 8. Fee Management

Primary navigation is now Fees / Charges. Scope belongs to the create/edit form. Configured fees show billing method, amount, year, term, scope, and active status, with View/Edit, preview, safe deletion, and activation/deactivation actions. Used definitions retain backend protection against rewriting their amount or terms; changed obligations require a new definition.

Generation begins from a fee preview and requires the existing explicit confirmation and preview token. Charges can be filtered by year, term, fee, historical class, and student name/admission. Historical class filtering uses enrollment overlap with the generated billing period, including learners enrolled after the period's first day. Legacy APIs and legacy fee management remain available.

## 9. Amount controls

Relevant finance number inputs use `step=1` and a zero step base, so native arrows advance 75 to 76. Form validation temporarily uses `step=any` while checking validity, then restores 1, permitting typed cents such as 75.50 while retaining required/minimum constraints. The backend continues enforcing currency precision and positive fee amounts.

## 10. Link styling

Global normal and visited anchors share the application blue. Low-specificity visited styling lets intentional component colors continue to override it. Hover, active, and focus-visible states are defined; keyboard outlines are preserved.

## 11?13. Student Account Statement and letterhead

A shared read-only statement endpoint and screen serve school administrators and linked parents. Student detail and student finance pages link to Account Statement. Each selected child in the Parent Portal has the same option.

The document includes school name, configured logo/address/phone/email, statement title, learner name/admission/current-class label, academic filters, selected date period, and generated timestamp. Missing optional details are omitted. Columns are Date, Reference, Description, Debit / Charges, Credit / Payments, and running Balance. Summary shows opening balance, charges, payments, adjustments/reversals, and closing balance in school currency.

Charges use original assignment dates and fee references. Payments use receipt numbers (with existing payment reference/ID fallback). A reversed payment remains visible as its original credit plus a compensating debit on its reversal date. Independent adjustment ledger entries are included once; mirrored charge/payment ledger rows are not double-counted. No separate statement balance is stored.

Year/term filters select the obligations and their related payments/reversals. Date range then determines opening and closing balance within that selected academic context. All history is the default. The screen explains these semantics. Browser Print / Save PDF hides controls/application content and prints the letterhead, transactions, totals, and generated date. No PDF dependency was added.

Parents have GET-only access after a server-side parent/student link check. Administrators are scoped by their school. Foreign children and unrelated parents receive 404, not a report constructed from a trusted frontend student ID.

## 14. Backend files

Modified:
- `backend/core/models.py`: timetable scope.
- `backend/core/academics_api.py`: scope serialization, dynamic class names/filtering.
- `backend/core/timetables.py`: scope resolution and conflicts.
- `backend/core/views.py`: legacy and parent timetable applicability.
- `backend/core/serializers.py`: field-specific fee term validation and historical charge class IDs.
- `backend/core/urls.py`: read-only reporting routes.

Added:
- `backend/core/reporting_api.py`: attendance history, shared statement calculation, authorized reporting views.
- `backend/core/test_usability.py`: attendance, timetable, fee, statement, tenant, reversal, and historical class regression tests.
- `backend/core/migrations/0021_timetable_scope.py`.

## 15. Frontend files

Modified:
- `frontend/src/App.jsx`, `frontend/src/App.css`.
- `frontend/src/components/TimetableEditor.jsx`.
- `frontend/src/pages/AttendancePage.jsx`, `TimetablesPage.jsx`, `AcademicRecordsPage.jsx`, `HomeworkPage.jsx`.
- `frontend/src/pages/FeeManagementPage.jsx`, `FinanceRecordsPage.jsx`.
- `frontend/src/pages/ParentDashboard.jsx`, `StudentDetailPage.jsx`, `StudentFinancePage.jsx`.
- `frontend/src/academics.test.js`.

Added:
- `frontend/src/components/AttendanceHistory.jsx`.
- `frontend/src/components/SubjectPicker.jsx`.
- `frontend/src/components/moneyValidation.js`.
- `frontend/src/pages/AccountStatementPage.jsx`.

## 16?17. Migration and compatibility

Only migration 0021 was created. It adds scope and classifies existing one-class timetables as SINGLE; other existing definitions remain MULTIPLE. It preserves timetable IDs, entries, class links, and existing migrations. No financial or attendance migration was created.

Read-only `showmigrations` confirmed application migrations 0001?0020 are applied and 0021 is pending. This run did not apply 0021 to the application database. It must be applied as part of the eventual release before the changed timetable API runs. All migration execution for certification occurred in isolated PostgreSQL test databases.

Existing financial records, historical attendance, parent/student links, and subject references were not rewritten. Offline attendance storage and queued API format remain compatible.

## 18?20. Verification

- Focused backend suite: Attendance/Academics, fee management, safe fee deletion, and new usability/statement tests **37 tests passed**.
- Full PostgreSQL Django suite: **152 tests passed**. Database vendor was explicitly verified as `postgresql`.
- Tests used the established fast test-only password hasher and cleared the throttle cache between tests; production settings were not changed.
- `manage.py check`: passed.
- `makemigrations --check --dry-run`: no changes detected.
- `git diff --check`: passed.
- Full frontend suite: **32 tests passed**, including **13 workflow/UI tests** in `academics.test.js`.
- Frontend lint and production build: passed.
- Existing non-blocking notices: backend test staticfiles directory warning; Vite static/dynamic import warning for the shared API client.

## 21. Remaining limitations

- Migration 0021 is pending on the application database; no deployment was performed.
- Whole-school applicability follows the active school class catalog because SchoolClass has no separate year/term membership history. The timetable's year/term still limits its schedule context. Explicit SINGLE/MULTIPLE scopes retain fixed class membership.
- Attendance history and statements require an online request; offline attendance capture and pending restoration remain supported. Selecting a new built-in/custom subject requires a connection; previously cached homework subject IDs remain usable offline.
- History/report responses load the requested range without pagination. Very large schools should narrow date filters; pagination/export batching can be added separately.
- PDF is browser print-to-PDF. Automated tests verify document content, controls, and print CSS; no physical printer or browser-generated PDF visual inspection was performed.
- Statement class is explicitly labeled current class. Historical attendance and charge-class filtering use enrollment history.
- No particular live browser/network failure was captured for the original timetable and fee reports; the confirmed code defects, payload behavior, and failure-path regression coverage are distinguished above.
