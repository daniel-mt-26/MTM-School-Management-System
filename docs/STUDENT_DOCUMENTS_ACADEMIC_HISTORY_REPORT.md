# Student fee documents and historical academic records

Implemented on 16 October 2026. No deployment, commit or push was performed. Existing uncommitted work was retained. The application database was not migrated or seeded; test writes used the separate local PostgreSQL test database.

## 1. Existing functionality reused

| Area inspected | Existing implementation and reuse |
| --- | --- |
| Fee structures and recurring fees | `Fee`, `RecurringFeeTemplate`, preview/confirmation workflows, monthly/termly/one-off billing and legacy monthly generation were retained. |
| Student charges | `StudentFeeAssignment` remains the obligation. Its student/fee uniqueness and existing immutable-charge API remain authoritative. |
| Payments and allocation | Each `Payment` already belongs to one charge. Existing partial-payment, overpayment protection, receipt creation and reversal workflows were reused. |
| Receipts | Existing receipt records, numbers, permissions and download routes remain. Rendering now shares the A4 document layer. |
| Statements | Existing school and parent statement endpoints and page were upgraded. No parallel statement ledger was introduced. |
| Balances | Existing balances, student finance profiles, ledger, cashbook and expenses remain accessible. New debtor projections read the same obligations and allocations. |
| Parent finance | Existing `ParentStudent` relationships continue to authorize statements and finance. Invoices add an explicit school-controlled access flag. |
| Results/report cards | Existing result review/publication/correction workflows and original report-card files/downloads were retained. History compiles their official values. |
| Branding | Existing school logo, name, address, phone, email and operational currency were reused. Optional document identity settings extend them. |
| PDF/Excel | Existing receipt PDF and attendance PDF/XLSX code was inspected. The new shared PDF renderer adds A4 pagination and wrapping; XLSX follows the existing dependency-free OOXML approach with numeric formatting. Attendance exports remain intact. |
| Tenant authorization | Existing role permissions and school/parent/teacher relationships authorize the new endpoints. Frontend school IDs never determine ownership. |
| Audit/idempotency | Existing `AuditLog`, `log_action`, transactions, uniqueness constraints and financial generation/payment workflows were reused. Invoice retries return the existing official document. |

Student Fee Management now exposes Fee Structures, Student Charges, Payments, Receipts, Invoices, Student Financial Statements, Outstanding Balances and Ageing Debtors. Existing ledger, expenses, cashbook, balance and legacy recurring-fee routes remain.

## 2. Ageing Debtors

`financial_reports.ageing_report` calculates unpaid obligations individually at the reporting date. It uses the configured fee due date, falling back to the original assignment date. Payment allocations stay attached to their original charges. A payment after the reporting date is excluded; a later reversal does not erase a payment from an earlier reporting date.

Buckets are Not Due, 0–30, 31–60, 61–90 and over 90 days. The extra Not Due column keeps future obligations distinct and makes buckets reconcile to total outstanding. Only learners with a positive net balance appear. Independent adjustments use their own original obligation dates; credit adjustments offset oldest remaining obligations without creating or moving payments. Mirrored ledger charge/payment/reversal entries are not counted again.

Filters cover academic year, term, historical class/grade enrollment, reporting date and student search. Class/grade uses the existing class model; there is no separate grade field in this repository. Displayed class labels identify the learner's current class. The shared `assignment_period` helper preserves the existing generated-period enrollment rules.

All displayed columns can be sorted. Header controls and the sort selector update the server sort, which is also used by PDF/Excel exports. Totals cover the displayed outstanding learners under the selected filters. They are not a whole-school income statement.

## 3. Invoice architecture

`StudentInvoice` references the existing billed assignment through a one-to-one protected relationship. One official invoice is issued per charge; term grouping remains available through list filters. Generating an invoice creates neither a charge nor a payment nor a ledger entry.

The invoice stores the original issued amount, currency, due date and a snapshot of its charge description, billing identity, academic context and school branding. Embedded logo bytes keep historical invoices printable after the school's uploaded logo is replaced. Current allocated payments and payment status are projected from the original payment records. Subsequent independent account adjustments remain visible on the student statement rather than rewriting an issued invoice.

List queries select only the necessary JSON billing metadata, avoiding loading embedded historical logo data for every listed document.

## 4. Invoice numbering

Numbers are school-local and readable: `INV-000001`, `INV-000002`, etc. Schools have independent `SchoolInvoiceSequence` records. A transaction locks the owning school before reserving a number, including first use. Database uniqueness enforces `(school, number)` and a single invoice per assignment.

Concurrent retries for the same obligation return one invoice and consume one number; different concurrent obligations receive distinct numbers. The official invoice model and API do not allow editing or reissue. Repeated generation is an idempotent retrieval of the existing invoice, not a new issue.

## 5. Invoice PDF structure

The invoice follows the written reference structure: left logo, prominent school identity and optional motto, contact details and brand divider; prominent invoice number; two-column learner/billing and invoice/contact details; quantity, description, unit amount and total; and subtotal, payments allocated, outstanding balance and total amount due.

No reference images were attached, so image-level visual matching could not be performed. No Beavers identity is hardcoded. No VAT/tax is invented: MTM currently has no legitimate configured VAT calculation to render.

## 6. Student statement improvements

The original statement now provides school letterhead, learner identity, academic context, statement date, applicable earliest unpaid due date, opening balance, current charges, payments, adjustments/reversals, closing balance and total amount due. The transaction table includes term/period, original date, reference, description, debit, credit and running balance.

Academic year/term select their calendar boundaries. Custom start/end dates override the corresponding boundary. Opening balance includes all earlier account transactions, including previous academic years. Payments against an older year's fees remain dated when paid. Full history removes the period restrictions. This intentionally improves the former behavior that first excluded obligations from other academic contexts and could omit a real previous balance.

Payment and reversal events both remain in transaction history on their own dates. Charges and payments are not duplicated from their mirrored ledger entries. Running balances reconcile to opening balance plus debits less credits. A net credit/settled account has no amount due or unpaid due date. The chronological statement table cannot be resorted into a misleading running-balance order.

## 7. Outstanding balances

The dedicated view shows admission number, learner, class, guardian, billed charges, actual allocated payments, adjustments and outstanding balance. It uses the same projection as Ageing Debtors and supports the same filters, sorting, PDF, Excel and print actions. Existing authoritative student/assignment totals also include independent ledger adjustments without relabeling them as billed income or cash.

The cashbook continues to use actual valid non-reversed payment records. Billed charges, cash collected and receivables stay separate.

## 8. Historical Academic Records

History compiles published report cards across academic years and terms, with classes attended, subjects, marks, percentages, preserved official grades and officially published comments. Draft/unpublished reports are excluded. It does not replace the result engine or redesign the original report-card files.

`ReportCardPublication` retains immutable publication versions. Publishing a report captures the official result values and comments. The existing correction workflow preserves the preceding publication, hides the report while correction is underway, and captures another version when republished.

School grading bands are optional and have no invented default. Newly published results freeze their grade and grading configuration. Later grading configuration changes do not recalculate old grades. Legacy grades absent from the database remain blank; marks/comments and original uploaded report files are preserved. No grades are inferred from historical PDFs.

## 9. Parent Portal

Parents retain statement access for linked children and gain historical academic records for linked children. Invoice access defaults to disabled and can be enabled in School Settings → School Documents. Both invoice lists and individual JSON/PDF downloads enforce the flag and current child links. Removing a link removes access. Parents cannot generate or change invoices.

Teachers receive no financial document access. Academic history uses existing teacher class/subject assignments and removes unassigned subjects, school-wide report comments and guardian fields. Platform administrators gain no new access to private school finance or academic history.

## 10. Shared document branding

`documents.py` provides reusable letterheads, tables, summaries, A4 pagination, monetary display and private downloadable responses. `SchoolDocumentSettings` adds motto, website, additional contacts, contact person, validated brand color, parent invoice access and optional grading bands. Existing identity/contact/logo settings remain in the existing school profile.

Invoices, statements, debtor reports, academic history and existing receipt downloads use the shared renderer. Receipt records/numbers/statuses and routes remain unchanged. Original report-card file downloads are retained for the future visual-template work. Missing/unavailable optional logos do not prevent otherwise valid documents from being produced.

## 11. PDF, Excel and print

PDFs use ReportLab with A4 portrait documents and A4 landscape debtor reports, consistent margins, wrapping cells, repeating table headers and page numbers. Small summaries remain together and are attached to the relevant final transaction/line where space permits. Excel uses actual numeric cells with two-decimal formatting; user text is written as strings rather than spreadsheet formulas. Statement exports include opening balance, chronological transactions and summary totals.

Print controls use the same visible document data. Financial filter changes hide stale figures and disable print/export until the corresponding response arrives. The styling hides navigation and allows table headers to repeat.

Conventional aged-receivable layout inspiration was checked against [Xero's aged receivables documentation](https://central.xero.com/s/article/Aged-Receivables-Detail-report-New). PDF pagination uses the documented [ReportLab table mechanisms](https://docs.reportlab.com/reportlab/userguide/ch7_tables/). No external institution branding or wording was copied.

## 12. Migrations and dependencies

- `0028_student_documents`: additive result grade/snapshot fields and new document-settings, invoice-sequence, invoice and publication tables, with protected relationships and uniqueness constraints.
- `0029_preserve_published_academic_history`: copies existing eligible published marks/comments into initial publication snapshots. It updates/deletes no existing result, student, report-card, parent-link or financial row; repeat execution does not create duplicate versions. Its reverse data operation is deliberately a no-op.
- Runtime PDF dependency: `reportlab>=4.4,<5` in root `requirements.txt`.
- Test dependency: `pypdf>=6,<7` in `backend/requirements-test.txt`.

Both migrations ran on the PostgreSQL test database. The application database remains unchanged and has existing pending migrations `0022`–`0027` before these new migrations. Applying the prerequisite migration chain is still necessary before using these features against that database. No deployment was attempted.

## 13. Backend files changed in this batch

New implementation files: `backend/core/documents.py`, `financial_reports.py`, `finance_documents.py`, `academic_history.py`.

Extended existing files: `backend/core/models.py`, `finance.py`, `reporting_api.py`, `serializers.py`, `views.py`, `staff_api.py`, `urls.py`.

Migrations/tests/dependencies: `backend/core/migrations/0028_student_documents.py`, `0029_preserve_published_academic_history.py`, `backend/core/test_student_documents.py`, `test_usability.py`, `tests.py`, `backend/requirements-test.txt`, root `requirements.txt`.

`staff_api.py` and other earlier changes already existed as uncommitted work. This batch builds on them without committing or resetting that work.

## 14. Frontend files changed in this batch

New pages: `frontend/src/pages/InvoicesPage.jsx`, `DebtorsPage.jsx`, `StudentStatementsPage.jsx`, `AcademicHistoryPage.jsx`.

New shared components: `frontend/src/components/StudentFeeNavigation.jsx`, `SchoolLetterhead.jsx`, `DocumentSettingsPanel.jsx`.

Extended files: `frontend/src/App.jsx`, `App.css`; pages `AccountStatementPage.jsx`, `FeeManagementPage.jsx`, `FinancePage.jsx`, `FinanceRecordsPage.jsx`, `AcademicsPage.jsx`, `StudentDetailPage.jsx`, `ParentDashboard.jsx`, `SchoolSettingsPage.jsx`, `TeacherPortal.jsx`; tests `academics.test.js` and `student-documents.test.js`.

## 15. Security and financial regression coverage

Tests cover cross-school IDs and calendar/class filters; forged tenant fields; parent access flags, linked-child list/detail/download access and link revocation; teacher/platform financial denials; teacher subject restrictions; tenant-local numbering and database uniqueness; concurrent duplicate/different-obligation generation; immutable invoice amount/identity/description/logo; original payment allocations and reversals; age bucket boundaries and future-due balances; as-of payment/reversal timing; shared outstanding calculations; previous-year statement balances and original payment dates; running/closing balances; mirror-entry de-duplication; credit-adjusted settled accounts; immutable historical grades/comments and correction versions; published-only multi-year history; idempotent legacy backfill; valid branded A4 PDF/Excel output; repeated PDF headers and summary placement; and existing receipt history.

Audit events include invoice generation/download, statement export, report publication/history download, document settings changes and the existing financial workflows. They record concise metadata rather than passwords, tokens or request bodies.

## 16. PostgreSQL results

Final full PostgreSQL suite: **253 passed, 0 failed**, in 74.189 seconds. This includes the 26 tests in the new document/security module. An earlier focused finance/document/statement/teacher run also passed all 57 tests then present. The final full run includes subsequent receipt, pagination, preservation and settled-account regressions.

Command: `python manage.py test --settings=config.test_settings --noinput --keepdb`. The PostgreSQL test database is separate from the unchanged application database. The final log is `backend/.local-provisioning/student-documents-postgresql-tests.log`.

## 17. Frontend tests, lint, build and checks

| Final validation | Result |
| --- | --- |
| `npm test` | **69 passed, 0 failed**, including 10 new document UI tests. |
| `npm run lint` | Passed. |
| `npm run build` | Passed; 117 modules transformed. Non-blocking bundle/import warnings are listed below. |
| `python manage.py check` | Passed, no issues. |
| `python manage.py makemigrations --check --dry-run` | Passed, no changes detected. |
| `git diff --check` | Passed. Existing Windows line-ending advisories are not whitespace errors. |

Frontend tests exercise navigation, invoice generation/list/detail, read-only parent access and denial, debtor filters and sorting, statement filters and protected export parameters, history display, settings and prevention of stale financial exports. Existing UI/offline/intake/teacher tests also pass. The final frontend log is `backend/.local-provisioning/student-documents-frontend-tests.log`.

## 18. Known limitations

- The two reference images were not attached; invoice/statement structure follows the written specification. Pixel matching awaits those images.
- Invoices are issued per billed obligation. There is no invented grouped-invoice, VAT, cancellation, email-delivery or reissue workflow.
- Legacy grades absent from stored result data cannot be recovered automatically from old report-card files; those files remain intact.
- Debtor class labels show current class; class filters use enrollment history during the billed period. Class and grade share the existing class model.
- Unassigned adjustments have no academic year/term attribution, so academic-obligation-filtered debtor reports exclude them; full-account statements retain them by actual date.
- PDFs were programmatically validated for A4, branding, embedded image presence, page headers and summaries. No manual browser/PDF screenshot review is claimed.
- The production build emits warnings about its approximately 502 kB main bundle and an existing static/dynamic import overlap. These are non-blocking; deployment was not performed.
- The application database still needs its pending prerequisite and new migrations before runtime use.

## 19. Future report-card template

The original report-card workflow and uploaded official files remain in place. Historical academic snapshots and compilation are ready to feed the future template. The final official report-card visual design and image-specific matching remain for the user-supplied template; this batch does not claim to finalize that design.
