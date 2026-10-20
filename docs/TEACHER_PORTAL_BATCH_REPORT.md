# Teacher Portal development batch — 14 October 2026

Implemented locally. No deployment, commit or push. Pre-existing intake changes and the existing edit to migration 0004 were preserved.

## Architecture and behavior

1. **Existing authentication:** explicit application roles, school-owned administrator/parent profiles, SimpleJWT access/refresh tokens with live `token_version` checks, forced password change, account/school suspension policy. Django superuser status does not grant an application role.
2. **Teacher role:** `teacher`, routed to `/teacher`, accepted only with an active Teacher profile and operational school. Password-change gating applies before academic access.
3. **Teacher model:** protected User/School ownership, active status and creation/update timestamps. Frontend school IDs do not determine ownership.
4. **Assignments:** one TeacherAssignment per teacher/class, multiple classes supported, subject authorization uses ClassSubject records including academic year. Empty subject assignments permit class-level tools but do not grant marks access to every subject.
5. **Management UI:** `/school/teachers` centralizes creation, profile edits, activation, deactivation, class/year/subject assignments, username, last login and password reset. No delete-account action.
6. **Teacher navigation:** Dashboard, My Classes, Attendance, Homework, Results, Report Comments, Timetable, Students, Announcements, Resources and Profile. Role guards prevent entry to admin/parent/platform routes.
7. **Homework:** removed from the main Academics navigation; existing admin oversight route remains. Teachers create drafts, publish, edit their own drafts and close published work. Existing homework and protected attachments remain supported.
8. **Attendance:** existing roster and bulk endpoints now allow academic staff; every teacher request checks assigned-class ownership before processing or replay. Existing enrollment validation, full-roster saves, conflict detection and idempotency are reused.
9. **Register:** Attendance History offers a Monthly Register view with academic year, term, class, month and calendar-year filters. Actual month lengths include leap February. Historical enrollments are selected by enrollment dates. P/A/L/E codes, counts and percentages appear; missing entries are blank. Percentage is `(Present + Late) / all marked days × 100`, including Excused in the denominator. Unmarked days are excluded.
10. **Exports:** authenticated PDF and XLSX endpoints use the same register authorization. PDF repeats metadata and day headings on landscape pages. XLSX uses separate day cells and numeric totals. Print view uses the register component. School, class, year, term, month, teachers and generated date are included.
11. **Results:** new API-created results start Draft; teacher submits; admin approves, returns to Draft or publishes. Submitted/approved/published edits are denied. Explicit admin correction requires a reason, saves the complete original result in ResultRevision, retracts its report, and reopens Draft for another review cycle.
12. **Report comments:** assigned teachers create/edit structured enrollment/term comments. Published report comments are locked. Admin controls publication and cannot notify parents about a draft. Parents receive only published reports and their comments. Actual report-file visual templates are unchanged.
13. **Timetable:** teacher read-only view includes assigned-class shared timetable periods, expanded per authorized class. Personal view filters teaching subjects by class/year assignment; a separate view shows full assigned-class timetables. Non-subject class activities remain visible. Admin retains master editing.
14. **Sorting:** SortableTable wraps existing tables and sorts React rows without replacing page filter/search state. Accessible headers expose ascending/descending indicators; numeric amounts/percentages, natural admission numbers and ISO dates are supported. Explicit sort values support formatted result percentages and report dates.
15. **Admin announcements:** separate `/school/teacher-announcements` supports all active teachers or selected teachers, including a single teacher; recipients are school-checked.
16. **Teacher announcements:** all assigned classes or selected classes, including one class. Recipient lists are validated; explicit school-wide audience parameters are rejected. Linked parents receive in-app notifications; teachers receive admin announcements in their portal.
17. **Resources:** protected download API for assigned classes/subjects, with PDF/DOCX/JPEG/PNG content validation and 10 MB maximum. Raw local resource media routes are denied, and response serializers do not publish storage URLs.
18. **Parent credentials:** new accounts use unique generated usernames where no username is supplied; generated passwords are hashed and returned only in the creation response. Existing ParentStudent links and multiple guardians are retained. Parent Details shows status, last login and reset; current passwords are never returned.
19. **Teacher credentials:** normalized `firstname.surname`, numeric collision suffixes, database uniqueness with savepoint/retry handling, secure server-generated temporary password, forced first-login change and one-time display.
20. **Admin reset:** teacher and parent reset actions lock the User row, generate a new temporary password, require password change and increment `token_version`. Existing authorized platform school-admin reset workflow remains.
21. **Forgot password:** username/email neutral response; hashed random 45-minute, single-use token; five recovery requests/hour/IP; configured Django MAILERS email delivery. Tokens use URL fragments to avoid inclusion in HTTP URL logs and are removed from browser history by the reset page. Tokens carry the account version and become invalid after any other credential reset. Completion revokes JWTs and safely audits all roles.
22. **Inactivity:** 30 minutes, two-minute warning, Stay Signed In and Log Out. Pointer/keyboard/touch activity resets the timer; polling does not. Activity is shared across tabs for the same account. Focus checks elapsed time. Async profile refresh cannot restore a logged-out session.
23. **Offline/session handling:** teacher routes reuse OfflineProvider, IndexedDB caches and existing queues. Scope is user ID plus role. Inactivity logout clears auth without clearing queued work; protected route unmounts. Token refresh checks that it still belongs to the current session. Offline attachment uploads remain unsupported, as before.
24. **Attribution:** safe external “Powered by MDS” link in the shared app bottom area and teacher sidebar, covering login and all portals; no school setting changes it. Styling explicitly controls visited color.
25. **Auditing:** teacher creation/edits/status/assignments/resets, parent resets, result draft/edit/transitions/correction, comments, resource upload, announcements and password changes/recovery. Audit school may be null for platform credential actions. Passwords, tokens and request bodies are not logged by these features.

## Files and migrations

26. **Backend:** added `staff_api.py`, `staff_access.py`, `credentials.py`, `password_recovery.py`, `attendance_register.py`, `test_teacher_portal.py`; updated models, authentication, permissions, serializers, views, reporting API, URLs and settings. Added disposable-test settings/runner; updated existing credential tests to use newly issued tokens and generated passwords.
27. **Frontend:** added TeacherPortal, TeachersPage, TeacherAnnouncementsPage, ResultsReviewPage, ParentReportsPage, PasswordRecoveryPage, AttendanceRegister, Attribution, SortableTable, tableSort and inactivity utilities/tests. Updated App routing, authentication/client handling, admin/parent navigation and account pages, attendance/homework pages and existing data tables. Existing test loaders support explicit JSX component imports.
28. **Migrations:** 0024_teacher_portal_workflows adds teacher/assignment/comment/resource/announcement/recovery models and status/publication fields; 0025_credential_audit_scope permits platform credential audit entries; 0026_recovery_session_version binds recovery links to an account version; 0027_official_result_revision preserves published result corrections. All are additive or widen existing fields; no historical records are deleted or converted to Teacher.
29. **Compatibility:** existing results default Published and existing report cards default published in the additive migration, preserving prior visibility. New API-created results/reports are explicitly Draft. Attendance, finance, homework, timetable, relationships, offline queues, idempotency records and audit history are not rewritten. Migrations were exercised on PostgreSQL test databases; the application database has not been migrated. Its existing 0022/0023 intake predecessors are also pending.

## Verification

30. Focused backend: see final certification below.
31. Full PostgreSQL suite: see final certification below. `config.test_settings` uses PostgreSQL, MD5 hashing for disposable test users only, and clears throttle cache between test cases while retaining real throttling inside each test. Production password hashing is unchanged.
32. Frontend: see final certification below. Tests include rendered teacher navigation, sorting and indicators, register/exports, password recovery, fake-clock inactivity and scoped offline-work preservation, plus existing academic/intake/session/offline/finance tests.
33. Roadmap: `TEACHER_PORTAL_ROADMAP.md` lists all twelve requested future areas as FUTURE / PLANNED; no unfinished feature navigation was added.
34. **Operational limits:** email delivery requires a usable recipient email, SMTP configuration and `MTM_PASSWORD_RESET_ORIGIN` set to the frontend origin. Recovery deliberately does not emit secrets through console/file email backends; those accounts use admin-assisted reset. No live SMTP delivery or browser visual acceptance was certified. The primary `backend/venv` interpreter is missing; verification used the existing `venv-py314-backup`. Personal timetable derives teaching periods from subject assignments because the original timetable has no individual teacher identifier. PDF export uses the repository's minimal built-in PDF approach and substitutes unsupported characters with Latin-1 replacements. No lesson planning/messaging/analytics features were implemented.

## Final certification

| Check | Result |
| --- | --- |
| Focused Teacher Portal backend suite | 19 passed on PostgreSQL |
| Full Django PostgreSQL suite | 227 passed, 47.183 seconds |
| Full frontend suite | 59 passed, including 12 new teacher/security/UI tests |
| Frontend lint | Passed |
| Frontend production/PWA build | Passed; existing static/dynamic-import chunk warning only |
| Django system check | Passed, no issues |
| `makemigrations --check --dry-run` | Passed, no changes detected |
| `git diff --check` | Passed |

Backend commands used `backend/venv-py314-backup/Scripts/python.exe manage.py test --noinput --keepdb --settings=config.test_settings`. Connection inspection confirmed PostgreSQL on localhost. Tests used a disposable test database, not application records. The preserved test database includes migrations through 0027.

Frontend commands: `npm.cmd test`, `npm.cmd run lint`, `npm.cmd run build`. No dependencies were added.

The application database still has pending migrations 0022–0027. Applying those migrations and configuring actual SMTP/reset origin are operational prerequisites before using the new features there. No migrations were applied to the application database or any production database in this batch.

### Existing tables updated to use shared sorting

`AttendanceControls.jsx`, `AttendanceHistory.jsx`, `AcademicRecordsPage.jsx`, `AccountStatementPage.jsx`, `AuditPage.jsx`, `CommunicationPage.jsx`, `FeeManagementPage.jsx`, `FinanceRecordsPage.jsx`, `InventoryPage.jsx`, `ParentDashboard.jsx`, `ParentsPage.jsx`, `PlatformAuditPage.jsx` and `StudentsPage.jsx`. Existing intake list/detail tables also reuse the component while preserving their pending Phase 3 work, pagination and search.

Additional frontend integration changes include `offline/sync.js` (expected authenticated account on each queued request), `api/client.js`, `auth/AuthContext.jsx`, `auth/roleRoutes.js`, `App.jsx`, `App.css`, `AttendancePage.jsx`, `HomeworkPage.jsx`, `AcademicsPage.jsx`, `SchoolDashboard.jsx`, `LoginPage.jsx`, `ChangePasswordPage.jsx`, `ParentFormPage.jsx`, `ParentDetailPage.jsx` and `TemporaryPassword.jsx`.
