# Academics: curriculum, shared timetables and attendance

## Existing architecture and compatibility

`Subject` is school-owned. `ClassSubject` assigns an existing subject to a class
and academic year. Homework, results and report cards retain those references.
Previously, `TimetableEntry` represented one period for one class; there was no
named timetable definition. Attendance already used dated enrollment rosters,
atomic bulk submission, idempotency keys and version-based conflicts.

## Curriculum

`core/curriculum.py` contains the global Zimbabwe reference list specified for
this change, grouped by primary level and secondary category. It does not seed
every subject into every school. It also supplies eight non-subject activities.

`GET /api/school/subjects/library/` returns the reference library.
`POST /api/school/subjects/activate/` accepts a list of built-in `keys`.
Activation creates or reactivates the authenticated school's Subject records;
a case-insensitive existing name is reused without changing its ID or code.
Repeated activation is safe. Existing custom subjects remain supported.
`GET /api/school/subjects/?active=true` filters school subjects by active status.

The Timetables screen links to Subject Settings / Curriculum Setup. The main
Academics dashboard no longer contains Subjects or Class Subjects cards. Their
existing APIs and configuration screens remain accessible from Curriculum Setup.
No school-level curriculum classification exists, so administrators choose the
appropriate categories themselves; custom schools are not hard-filtered.

## Shared timetables

`Timetable` holds a name, school, academic year, term and many-to-many classes.
Entries are stored once and point to the definition. Their original class/year/
term fields remain for compatibility; class membership of a shared timetable is
authoritative. The editor supports one class, several classes or selecting all
currently active classes. Selecting all is a snapshot, not automatic membership
for classes created in the future.

`/api/school/timetable-plans/` provides list/create/detail/update/delete for named
definitions and nested entries. The legacy `/api/school/timetables/` period API
remains readable. Legacy period creation groups entries into single-class plans;
shared entries must be edited via their definition so changes affect all classes.
Parent timetable queries also include membership in shared plans.

Subject rows require an active school subject. Activity rows use the reference
activity list; existing custom labels survive migration and remain editable.
ClassSubject mappings are created when a school schedules a subject for a class,
using the existing mapping model. Removing a timetable does not remove those
mappings or any homework/results/report-card references.

Conflicts are checked against every attached class for the same year, term and
day, including legacy periods and other shared definitions. Intervals are
half-open: an 08:00–08:30 entry may be followed by an 08:30–09:00 entry. Internal
overlaps and invalid times are rejected. Error messages identify a class, day and
conflicting time range. School-row locks serialize timetable API writes; changing
class membership reruns conflict validation. Row IDs survive normal editing.

## Attendance

Attendance opens with the school's active class list. Selecting a class opens
the year, term and date controls and enrollment-derived roster. Present and
Absent are direct buttons alongside Late and Excused. Mark All Present changes
local state only; Save Attendance sends one complete bulk submission.

The existing device-local date default is retained (School has no time-zone
field). Administrators may select historical dates within the selected term.
No attendance eligibility, uniqueness, version-conflict or idempotency rule was
weakened. Existing Retry and Use server value controls remain.

Class/year/term lookups are cached in the existing account-scoped IndexedDB
store. Older roster-context caches are supported as a fallback. Offline class
selection opens its most recently cached roster and explicitly identifies that
date; users must check it before saving. Uncached classes/rosters show a clear
message. Bulk saves still use the existing durable sync queue and 409 handling.

## Migrations and rollout

- `0019_timetable_and_more`: adds the timetable definition, class mapping and
  nullable entry link. The existing unique-period constraint is recreated as
  deferred so valid time-slot swaps can occur within one transaction.
- `0020_copy_legacy_timetables`: groups existing entries by class/year/term,
  creates a single-class definition and copies its class relationship. Existing
  entry IDs, subjects, labels and times remain unchanged. The copy is idempotent.

Neither migration deletes subjects, class subjects, attendance, homework,
results or report cards. These migrations depend on the earlier, pending Finance
migrations 0017/0018. Application-database migration and deployment were not run.

## Verification

Backend tests cover opt-in activation, custom reference preservation, active
choices, multi-class membership, cross-school rejection, overlaps, editing,
legacy migration copying, parent visibility and all four attendance statuses.
The existing suite checks bulk idempotency, stale enrollments and 409 conflicts.
Frontend interaction tests cover navigation, timetable controls, class-first
attendance, explicit bulk save and cached offline queue behavior. Frontend tests
run sequentially to bound DOM-worker memory. Finance DOM assertions were also
changed to boolean comparisons so assertion failures do not dump React object
graphs while waiting for asynchronous deletion.

Final backend verification: 10 focused tests and all 144 PostgreSQL Django tests
passed. The isolated PostgreSQL test database used the fast test password hasher
and cleared the throttle cache between tests; production settings were not
changed. Django system checks, migration consistency and whitespace checks passed.
Frontend: all 24 tests passed and lint passed without warnings. Production build passed with the existing
static/dynamic-import chunking warning.

## Files changed for Academics

Backend: `core/models.py`, `core/serializers.py`, `core/views.py`, `core/urls.py`,
`core/academics_api.py`, `core/curriculum.py`, `core/timetables.py`,
`core/test_academics_improvements.py` and migrations 0019/0020.

Frontend: `src/App.jsx`, `src/pages/AcademicsPage.jsx`,
`src/pages/AttendancePage.jsx`, `src/pages/TimetablesPage.jsx`,
`src/pages/CurriculumPage.jsx`, `src/components/AttendanceControls.jsx`,
`src/components/TimetableEditor.jsx`, `src/components/timetableDefaults.js`,
`src/offline/attendance.js`, `src/academics.test.js`,
`src/components/FeeRecordActions.test.js` and the test command in `package.json`.
