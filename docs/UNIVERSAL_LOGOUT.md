# Universal logout — 26 October 2026

All four dashboards expose a **Logout** button in the shared account menu (in the teacher sidebar and in administrator/parent headers). The menu also remains available while dashboard data loads or fails to load.

Manual and automatic logout use the existing `AuthProvider.logout` and `tokenStorage.clear`. Both JWTs and the stored account identity are removed, the API role/scope is cleared, and existing route guards redirect to `/login`. Password-change and school-access-blocked routes also use the shared guard. No logout API endpoint or database operation was added.

The inactivity deadline is 600 seconds after the last trusted pointer, click, keyboard, scroll, wheel or touch event. API requests and automatic profile refreshes never record activity. One timeout schedules the two-minute warning and then the deadline. Listeners and the timer are cleaned up when the account changes or the provider unmounts. Focus, visibility changes and page restoration check the persisted deadline before new input can extend it. Session restoration checks local expiry/logout state before making a profile request, including while offline. A browser can suspend JavaScript in background tabs; the elapsed-time checks enforce expiry immediately when execution resumes.

Automatic logout displays exactly:

> Your session has expired after 10 minutes of inactivity. Please log in again.

Manual logout shows no inactivity warning. A fresh login starts a new deadline and clears the prior message. The two-minute warning is a status notification; genuine activity dismisses it without an API request.

Activity timestamps and logout signals are shared through localStorage, scoped by account ID and role. JWTs remain in each tab's sessionStorage. A per-tab logout-version snapshot detects a logout missed while a tab was suspended or closed. Received logout signals are not rebroadcast, and repeated logout calls are ignored. Other accounts and roles retain their independent sessions. Automatic logout preserves queued offline work under its existing account scope; manual logout retains each dashboard's existing offline-work policy.

## Changed files

- `frontend/src/auth/AuthContext.jsx`: common logout path, session restoration and inactivity lifecycle.
- `frontend/src/auth/inactivity.js`: 600-second deadline, trusted input, resume checks and tab synchronization.
- `frontend/src/api/auth.js`: clear saved account identity with JWTs.
- `frontend/src/components/AccountMenu.jsx`: shared Logout control.
- `frontend/src/pages/PlatformDashboard.jsx`, `SchoolDashboard.jsx`, `ParentDashboard.jsx`, `TeacherPortal.jsx`, `DashboardLayout.jsx`: use the shared menu.
- `frontend/src/App.jsx`: guard password-change and school-access-blocked pages.
- `frontend/src/App.css`: account-menu layout.
- `frontend/src/auth/inactivity.test.js`: deterministic deadline, trusted activity, independent tab storage, suspension and cleanup tests.
- `frontend/src/auth/logout-ui.test.js`: all four real dashboards with AuthProvider, JWT storage, route guards and login page; API calls use test responses.
- `frontend/src/teacher-ui.test.js`: move the previous 30-minute inactivity test into the universal logout tests.
- `docs/TEACHER_PORTAL_BATCH_REPORT.md`: update the previous inactivity description.
- `docs/UNIVERSAL_LOGOUT.md`: implementation and validation report.

## Validation

Run from `frontend`:

```text
npm.cmd test
npm.cmd run lint
npm.cmd run build
```

Tests cover manual and automatic logout for every role, exact deadline boundaries, all activity event types, ignored synthetic/background activity, activity shared between tabs, manual and automatic logout signals, account/role isolation, missed logout events, suspended-tab return, expired reload before API access, fresh login, queued-work isolation, late profile responses, StrictMode and cleanup. Browser behavior is modeled with separate event targets/session storage and a shared localStorage store; UI integration tests run in JSDOM. No live accounts or database data are used.

Final results:

| Check | Result |
| --- | --- |
| Full frontend suite (`npm.cmd test -- --test-reporter=dot`) | 118 passed; includes 38 universal logout tests |
| ESLint (`npm.cmd run lint`) | Passed |
| Production/PWA build (`npm.cmd run build`) | Passed; warnings about the shared API client's mixed static/dynamic imports and a bundle exceeding 500 kB |
| `git diff --check` for changed frontend/documentation files | Passed |

Implementation was completed locally. No school records, passwords or database data were changed. Pre-existing backend and demo-seeding edits were preserved. No deployment or push was performed.
