# Admissions and enquiries administrator dashboard: Phase 3

Implemented in the existing MTM React frontend. The Beavers and MDS websites were not modified. Existing uncommitted Phase 1 backend files and unrelated repository changes were preserved. No deployment, GitHub push, production migration, student creation or automatic enrolment was performed.

## Architecture inspected

SchoolDashboard uses navigation cards, not a sidebar. Existing student/profile layouts, table wrappers, form controls and colours are reused. AuthProvider, ProtectedRoute and apiClient retain existing JWT session restoration, refresh, expiry, password-change and suspended-school behaviour. New routes are restricted to `school_admin`, outside SchoolOfflineShell/OfflineProvider and separate from all Parent Portal routes.

The Phase 1 report and actual intake API, serializers, permissions, security and review services were inspected. Lists and histories return DRF `count`, `next`, `previous`, `results`, with 25 records per page. Status filtering is implemented server-side; there is no server search. Private responses use snake_case and `Cache-Control: no-store, private`. Review is POST, with a required current integer `version` and optional `status`/`note`.

## Files created

- `frontend/src/api/intake.js`: allowlisted endpoint helpers using the existing authenticated client, no-store requests, 20-second abort timeout, safe errors, current-page search and status metadata.
- `frontend/src/components/IntakeOnlineBoundary.jsx`: online-only route boundary; disconnecting unmounts sensitive views and reconnecting loads fresh records.
- `frontend/src/pages/IntakeListPage.jsx`: shared admissions/enquiries list with loading/error/empty states, local search, server status filters, refresh and pagination.
- `frontend/src/pages/IntakeDetailPage.jsx`: complete application/enquiry details, confirmation dialog, notes, status actions, histories, pagination and conflict recovery.
- `frontend/src/intake.test.js`: 13 new frontend tests using existing test tooling.
- `frontend/scripts/check-intake-browser.mjs`: real-backend synthetic browser workflow and accessibility test; expiry responses are mocked only in this test.
- `docs/INTAKE_ADMIN_PHASE3.md`: this report.

## Existing files modified

- `frontend/src/App.jsx`: four protected intake routes and online boundary.
- `frontend/src/pages/SchoolDashboard.jsx`: Admissions and Enquiries cards with professional SVG icons.
- `frontend/src/App.css`: scoped intake status indicators, forms, pagination, dialog, focus and mobile rules using the existing palette.

No dependencies, authentication infrastructure, backend models/APIs/permissions, student/parent functionality, service worker configuration or offline queue implementation were changed.

## Routes and features

| Route | Features |
| --- | --- |
| `/school/admissions` | Reference, student, requested grade, guardian, phone, submitted date, status; Pending/Approved/Rejected filters; pagination and clearly labelled current-page search. |
| `/school/admissions/:intakeId` | Full pupil/guardian/contact/address and optional previous school/information; dates, status, history; confirmed approval/rejection and private notes. |
| `/school/enquiries` | Reference, sender, subject, phone, submitted date, status; New/In Progress/Resolved filters; pagination and current-page sender/reference/subject search. |
| `/school/enquiries/:intakeId` | Full message/contact details, status updates, private handling notes and paginated handling history. |

Search does not claim to cover all server records. Status filters do cover the school's matching records through the backend. Pagination reconstructs its own numeric page parameter, never follows a response URL to another origin. Dates are displayed in Africa/Harare. History displays the actual administrator ID supplied by the API; no staff names or lookup capability were invented. Assignment controls were not added because they were not requested.

## API integration

Existing `VITE_API_BASE_URL` and apiClient are reused. No new environment variables or separate login were introduced.

- GET `/school/applications/?page=N&status=...` and `/school/enquiries/?page=N&status=...` (under the existing `/api` base).
- GET each `/{uuid}/` detail and `/{uuid}/history/?page=N`.
- POST each `/{uuid}/review/` with `{version, status?, note?}` only.

No school/tenant ID is sent. UUIDs, supported kinds, statuses and page numbers are checked locally; authoritative validation and permissions remain server-side. JWTs are attached/refreshed by the existing client. Expiry uses the existing failure/logout handler and protected-route redirect.

Only a valid backend detail/review response with the correct record ID, status and incremented version updates the screen or shows a saved notice. Pending updates lock the controls and use a single-flight ref guard. Native dialogs require explicit confirmation, focus Cancel initially, support Escape cancellation before saving, restore focus and expose a focusable pending message while saving. Internal note text is submitted only through the authenticated review API.

A 409 stale version blocks further writes until an explicit fresh GET. Network/server failures after POST also block writes because the update may already have committed. Reload discards the unsaved draft and refreshes history; a stale/uncertain POST is never automatically replayed. Local validation and backend 400 errors permit correction without claiming success. Approval is a review decision only; no Student, Parent or enrolment API is called.

## Confidentiality and permissions

Intake data lives only in mounted React state. Leaving views, ending the authenticated session, changing account or disconnecting unmounts the relevant data. Pending requests are aborted/ignored on unmount. Request options use `cache: no-store`; the existing service worker has no runtime API caching and excludes `/api/` navigation fallback. No intake code imports IndexedDB persistence, cacheValue, enqueueOperation or OfflineContext. Existing JWT session storage remains unchanged; admission/enquiry bodies and notes are not stored in localStorage, sessionStorage, IndexedDB or the offline queue.

Phase 1 `IsSchoolAdministrator` permits all existing school administrators with the required profile and no forced password change to review their school's applications/enquiries. This is preserved. There is no separate admissions approver permission or role; narrowing that policy requires an explicitly reviewed backend permission change. Platform administrators and parents do not receive these routes. Cross-school access remains 404 through the existing school-scoped queryset. No tenant isolation was weakened.

## Validation

- Frontend test suite: 47 tests passed (34 existing and 13 new intake tests).
- ESLint and production frontend/PWA build passed. The build retains the existing informational warning that the authenticated client is both statically and dynamically imported; it does not prevent the build.
- All 30 existing Django intake tests passed in a disposable test database inside the isolated local PostgreSQL cluster on port 55482. Coverage includes tenant/role restrictions, revoked/expired credentials, review history, stale versions, duplicate/public submission protection and unchanged enrolment behaviour. Ordinary MTM development/production data and schemas were not changed.
- Browser workflow used real Django JWT authentication and APIs against synthetic schools/records in the isolated test database. Confirmed approval, rejection, internal notes, history, all enquiry statuses, a real concurrent review conflict, explicit reload and real cross-school API/detail rejection passed. Anonymous routes redirect to login. Expiry was simulated only in the automated test and confirmed existing logout/token cleanup.
- Seven automated WCAG A/AA scans passed in each development and production-format browser run, covering list, modal and detail views at desktop/tablet/mobile widths including 320, 375, 768 and 1440 pixels. No runtime errors or horizontal page overflow occurred; table regions scroll with keyboard access on narrow screens. Modal Escape/cancel/focus restoration passed. Browser inspection found no intake records in localStorage, sessionStorage, IndexedDB caches/queue or CacheStorage; offline transition removed the intake view and reconnect loaded fresh records. The production-format preview was built separately in TEMP against the isolated backend; its service worker was confirmed to control the tested page, with no intake API responses cached. MTM's normal production build was left intact.
- Final database inspection confirmed no student or enrolment created by administrator review. Browser test artifacts are in TEMP, not the public site or repository. Tests never sent real email.
- `git diff --check` passed. No Beavers or MDS files changed, and nothing was deployed or pushed.

Automated accessibility scans do not replace manual assistive-technology review.

## Configuration and remaining decisions

The dashboard needs the existing correctly configured MTM HTTPS `VITE_API_BASE_URL`, matching authenticated frontend CORS origin, normal JWT session settings and released Phase 1 migration. No new frontend secret, tenant configuration or dashboard environment flag is required. Do not point synthetic submission/review tests at a production tenant.

Public intake collection remains separately dependent on approved Beavers tenant binding, privacy/version/retention settings, website/CORS origins and Turnstile configuration. Email requires the existing verified SMTP/outbox worker setup. This phase does not enable collection, change those gates or provide automatic enrolment.

No unresolved tenant-isolation defect was found in the tested workflow. The broad existing school-administrator review permission remains the main policy decision to confirm before operational use. Whole-database search is not implemented by the backend; current-page search is explicitly labelled.

To reproduce unit checks, run `npm test`, `npm run lint` and `npm run build` in `frontend`. The browser script takes Playwright and axe module paths plus a temporary synthetic fixture JSON (`admin` access/refresh tokens and the application/enquiry/foreign IDs/references). Set `INTAKE_TEST_FRONTEND` and `INTAKE_TEST_API` only to isolated test servers; defaults are loopback ports 4176/8053. Set `INTAKE_TEST_REQUIRE_SW=true` when checking a local production-format preview to assert service-worker coverage. The script refreshes only its synthetic session before testing. No browser-test dependencies were added to the application.
