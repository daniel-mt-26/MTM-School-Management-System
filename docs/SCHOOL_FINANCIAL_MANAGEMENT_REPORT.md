# School Financial Management implementation report

Implemented 16 October 2026. This batch extends the existing finance and student-document work. No deployment, commit or push was performed. Existing uncommitted work and the application database were retained; validation writes used the separate PostgreSQL test database.

## 1. Existing architecture found

`Payment` is the canonical receipt of student money and references `StudentFeeAssignment`. `Receipt` already has a one-to-one payment relationship. The financial ledger mirrors charges/payments and preserves reversal entries. Existing services handle assignment uniqueness, partial payments, receipt creation, reversals and financial totals. `Expense` already stores school operating costs and supports audited edits without deletion. Finance already offered a daily cashbook, student balances, ledger and cashbook endpoints.

The prior batch supplied invoice snapshots, ageing/outstanding projections, statements, tenant permissions, shared school letterheads, A4 PDF tables and numeric/formula-safe Excel exports. Those services are reused. The new reporting service does not create a second cash ledger or copy payment/receipt records.

Finance now exposes both requested groups: Student Fee Management retains Fee Structures, Charges, Payments, Receipts, Invoices, Statements, Outstanding Balances and Ageing Debtors. School Financial Management exposes Income Records, Expenses, Cash Books, Monthly Reports, Annual Reports and Financial Dashboard. Cash Received, Expense Reports and Accounts/Categories supplement those sections. Previous ledger, balance and legacy daily-cashbook routes remain available. **Bank Reconciliation = FUTURE.**

## 2. Income implementation

Income Records projects existing student payments and actual non-student income. Rows expose transaction date, reference, source, category, description, method, account, signed amount, student/admission and historical billed class where relevant, receipt, receiver and linked canonical record.

`ManualIncome` is limited to non-student receipts. The API rejects student/payment links and frontend school ownership fields. Learner money is recorded through Payments and appears automatically once. Manual receipts have no invented student or payment receipt. New income records are immutable; explicit audited reversal preserves the original record.

New payments can select a school-owned cash/bank account and income category. Unclassified historical payments remain grouped as School Fee Payments; no transport classification or bank account is inferred from free-text descriptions. Configured categories can distinguish transport and other receipts going forward.

The existing school-currency lock now includes expense-only and manual-income-only history, preventing historical amounts from being relabelled under a different operational currency.

## 3. Expense improvements

The existing Expense model/API remains authoritative. Additive fields provide account, configured expense category, supplier/payee and reversal metadata while retaining existing dates, legacy categories, currency, description, payment method, reference, supporting notes, creator and timestamps.

The upgraded expense screen supports creation, edits, filtering, sorting, document uploads/downloads, history, reversal and exports. Every edit records an `ExpenseRevision` containing the previous field values before saving. Reversed expenses cannot be rewritten or deleted. Explicit reversal retains the original expense and records who reversed it, when and why. The legacy daily cashbook also excludes reversed expenses from its valid-record view.

`FinanceCategory` supports school-specific income/expense categories; existing expense choices remain usable. Used categories/accounts preserve their labels and type; they can be deactivated rather than renamed or deleted. New entries reject inactive or cross-school classifications.

Supporting documents reuse existing validated PDF/DOCX/PNG/JPEG file handling, up to 10 MB each and five files per expense. Files have generated private paths, authenticated school-scoped download endpoints and no public file URLs. Direct `/media/finance_documents/...` access is blocked, including development static serving. Supporting documents are preserved rather than expired like homework files.

## 4. Cash Book

`school_finance.cash_events` projects canonical payments, manual income and expenses into dated money-in/money-out movements. No report creates transaction or ledger rows. Each original record has a stable source/type/id reference. Corrections are distinguishable reversal movements, not duplicate payments.

Daily, monthly, annual, academic-year/term and custom periods are supported. Filters cover account, transaction type, category, payment method, search, student and historical class. Cash and bank are account types; other named accounts are supported. Legacy records without explicit account data remain Unassigned rather than being silently reassigned.

Opening balance includes earlier matching movements. Period money in/out and closing balance satisfy:

`closing = opening + period money in - period money out`

Running balances are computed chronologically before display sorting. Sorting keeps the same filters; each running balance retains its chronological meaning. Transaction filters produce a filtered movement balance rather than a reconciled bank balance. There is no fabricated initial bank balance, manual cash adjustment, account-transfer or bank-reconciliation workflow.

## 5. Payment/Cashbook linkage and reversals

Student payments appear by their existing payment/receipt reference. Original payment dates remain unchanged. An original movement is retained in its original period and offset on the actual reversal date. Other-income and expense reversals follow the same convention. Reports prior to a later correction preserve the earlier position; monthly movements add up to the annual position.

For example, a valid January payment of 25 reversed in February shows January collections of 25 and a February correction of -25, with annual collections of zero. A reversal-period net receipt can therefore be negative. The original is visibly marked reversed when applicable. These corrections are labelled; they are not presented as new student charges or ordinary expenses.

The existing idempotency mechanism now protects payment, expense and manual-income creation. It handles concurrent operation keys through a transaction savepoint and stores the rendered JSON response, including Decimal/date values, for reliable replay. Frontend financial-entry retries retain their operation key and disable duplicate clicks.

## 6. Monthly Financial Report

The monthly report uses a school-branded header, reporting month/date range, academic context and generated date; separate INCOME and EXPENDITURE tables; Actual values; section totals; a financial summary; and saved management Notes/Comments/Explanation.

There was no existing budget or revision model. The implementation uses the request's option B: Budget, Revised Budget and Variance columns are omitted until legitimate budget support exists. No budget values, percentages or variance explanations are invented.

Summary metrics are Billed Fees, Fees Collected/Cash Collected, Other Income, Total Cash Income, Operating Expenses, Operating Surplus/Deficit and Outstanding Receivables at period end. Categories reflect actual transaction classification. The notes are school- and period-scoped and audited when edited.

## 7. Annual Financial Report

Annual reports use either the calendar year or the selected academic year's configured date range. They apply the same accounting service as monthly reports, with income/expenditure categories, all summary metrics, notes and monthly breakdowns. Monthly billed, collected, other-income, expense and surplus values reconcile to the annual totals. Outstanding receivables remain a period-end snapshot rather than being summed across months.

Academic year/term filters select reporting calendar boundaries. Transactions retain their original payment/expense/charge dates, including payments against earlier-year fees. Financial reports do not filter out a real cash receipt merely because its underlying fee belongs to an earlier academic year.

## 8. Financial Dashboard

The dedicated dashboard shows explicit cards for Billed Fees, Cash Collected from Student Payments, Other Income, Total Cash Income, Operating Expenses, Operating Surplus/Deficit and Outstanding Receivables at Period End, plus category and monthly analysis.

All cards and tables use one validated reporting period. Academic year, term, month, daily and custom date ranges are supported where applicable. Calendar year is disabled when a selected academic year determines the annual period. Stale cards are hidden and print/export disabled until the newly selected report loads. No card labels a fee charge as cash received.

## 9. Cash Received Report

This report uses the same original receipt projection as Income Records, showing date, receipt number, learner/admission where applicable, source/category, description, method, account, signed amount, received by and linked record/reference. It includes actual non-student receipts without inventing child or receipt data. Method totals and a grand net total include labelled corrections on their actual dates.

Daily, monthly and custom ranges, search, method, account, category, student/class filters, sorting, PDF and Excel are available. Existing payment receipts are downloadable through the protected original receipt endpoint.

## 10. PDF templates

All new PDFs use the existing reusable `SchoolDocument` renderer: A4 landscape accounting tables, consistent margins, dynamic school branding, report title, reporting period, academic context, generated date, currency, repeated headers, wrapped cells, grouped totals and page numbers. Cash Received keeps dedicated student/receipt/receiver columns. Monthly/annual reports separate income, expenditure, summary and notes. Annual reports include a monthly table.

The attachment contained the written request only, so the monthly image could not be matched visually. Its described structure is followed, with unconfigured budget columns omitted. Existing student documents and receipt generation continue using the same branding engine.

## 11. Excel exports

Income, Cash Book, Cash Received, Expense, Monthly, Annual and Dashboard reports export real XLSX workbooks. They contain school/report titles, reporting dates and currency, structured transaction/category rows, numeric financial cells, totals, method summaries or monthly summaries, and management notes where applicable.

The shared Excel writer now supports a styled, bold accounting header, a title style and freezing through the actual report header row. Monetary cells use two-decimal numeric formatting and readable column widths. User text remains an inline string, never an executable formula. Totals are calculated server-side from the same records used by PDF and on-screen reports.

## 12. School branding

School logo, name, address, phone, email, configured website, optional motto and safe brand color come from the existing school profile/document settings. No Beavers or Environmental Trust identity is hardcoded. Reports use current school branding; the prior batch's issued invoice snapshots remain immutable.

## 13. Tenant security

All new school-wide finance endpoints require School Admin and derive the school from the authenticated administrator relationship. Parents, teachers and platform administrators receive no school-wide finance access. Account/category/student/class/year/term IDs are validated against that school. Income, expense, revision and supporting-document object lookups remain school-scoped.

New manual-income/configuration APIs reject submitted school ownership and actor fields. The existing expense API retains its established behavior of ignoring submitted school ownership/currency hints and deriving them from the authenticated administrator. Report query school IDs cannot override the authenticated scope. Existing parent access to linked-child finance/invoices/statements remains unchanged.

## 14. Audit changes

The existing append-only `AuditLog` helper records expense creation/edit/reversal, manual income creation/reversal, classification configuration changes, supporting-document additions, report-note updates and generated PDF/Excel reports. Existing payment creation/reversal and invoice/student-document audit events remain.

Expense prior versions preserve material details for review. Reports otherwise remain read-only aggregations. Audit metadata uses resource identifiers, report type, period and format; authentication tokens/passwords are not added to logs.

## 15. Migrations

`0030_school_financial_management` is additive: nullable account/category links on existing payments/expenses, defaulted expense reversal/payee fields, and new FinanceAccount, FinanceCategory, ManualIncome, ExpenseRevision, ExpenseAttachment and FinancialReportNote tables with protected relationships and scoped uniqueness constraints. It contains no deletion or rewrite of historical financial rows and no guessed account/category backfill.

The new migration runs on PostgreSQL during tests. The application database remains unchanged and still has earlier pending prerequisites beginning at 0022; those and 0030 must be applied before runtime use. No deployment or application-data migration was attempted in this batch.

## 16. Backend files changed

New: `backend/core/school_finance.py`, `school_finance_api.py`, `test_school_finance.py`, `migrations/0030_school_financial_management.py`.

Extended: `backend/core/models.py`, `finance.py`, `serializers.py`, `views.py`, `urls.py`, `idempotency.py`, `documents.py`, and `backend/config/urls.py` for private finance-file protection. Existing prior-batch modules are reused rather than rebuilt.

## 17. Frontend files changed

New: `frontend/src/pages/SchoolFinancialPage.jsx`, `SchoolExpensesPage.jsx`, `FinanceConfigurationPage.jsx`; components `SchoolFinancialNavigation.jsx`, `FinancialEntryForm.jsx`, `PaymentClassificationFields.jsx`; and `frontend/src/school-finance.test.js`.

Extended: `frontend/src/App.jsx`, `App.css`, `api/finance.js`, `pages/FinancePage.jsx`, `pages/FinanceRecordsPage.jsx`. README documentation now describes both finance groups and future bank reconciliation.

## 18. Focused tests

The main focused PostgreSQL run passed **53 tests**: 23 new school-finance tests, 26 existing student-document tests and four legacy finance-expansion tests. Coverage includes no copied cash events; exact billed/collected/receivable/expense/surplus values; opening/running/closing balances; dated reversals; monthly-to-annual reconciliation; period validation; historical classes; search/sort/category/method/account filters; concurrent income/expense replay; payment/receipt replay; immutable expense history; private file validation/download isolation; report notes; cross-school object manipulation; role denial; read-only exports; branding; repeated multi-page PDF headers; styled numeric Excel and frozen headers. The existing expense ownership/currency compatibility contract is also retained and verified.

A subsequent focused currency-history regression also passed, verifying that both expense-only and manual-income-only schools retain their historical operational currency. The new school-finance module now contains 24 tests, all included in the final full suite.

The new UI tests cover the requested navigation, explicit dashboard metrics, hidden budget columns, filters, sorting, annual academic scope, saved notes, protected receipts/exports, manual-entry replay keys, expense edits/documents, configuration deactivation, payment classification and rejection of unauthorized report access. Final full-suite results follow below.

## 19. Full PostgreSQL tests

Final full PostgreSQL suite: **277 passed, 0 failed**, in 86.061 seconds. This includes all 24 school-finance regressions and existing student-document, expense, tenant, academic, teacher, offline API and intake tests.

Command: `python manage.py test --settings=config.test_settings --noinput --keepdb`. The test database is separate from the unchanged application database. The final log is `backend/.local-provisioning/school-finance-postgresql-tests.log`. Final Django checks also passed with no issues, and migration drift reported no changes.

## 20. Frontend tests, lint, build and checks

| Final validation | Result |
| --- | --- |
| `npm test` | **81 passed, 0 failed**, including 12 new school-finance UI tests. |
| Focused school-finance UI tests | All 10 then present passed; two subsequent expense-report URL/filter regressions also passed in the full suite. |
| `npm run lint` | Passed. |
| `npm run build` | Passed; 123 modules transformed. |
| `python manage.py check` | Passed, no issues. |
| `python manage.py makemigrations --check --dry-run` | Passed, no changes detected. |
| `git diff --check` | Passed; existing Windows line-ending advisories are non-blocking. |

The final frontend suite includes existing student-finance, academics, offline, intake and teacher workflows. Financial UI coverage includes retaining operation keys after network failure, hiding stale metrics, protected exports/receipts, sorting with filters intact, and carrying the expense date/account selection into printable report URLs. The final frontend log is `backend/.local-provisioning/school-finance-frontend-tests.log`.

## 21. Known limitations

- Budget/revised-budget/variance functionality is intentionally absent, using the permitted hide-until-configured approach.
- Bank Reconciliation is FUTURE. No bank import, matching, transfer, cash adjustment or invented bank opening balance is implemented.
- Historical transactions without explicit account/category information remain unassigned/default-classified. Classification is captured for new entries rather than guessed from old descriptions.
- Reversal corrections affect their correction period; negative net receipts or net expenses can occur. These are labelled and preserve monthly/annual reconciliation.
- Cashbook balances reflect recorded history and selected transaction filters. They cannot recover cash movements predating MTM records.
- Expense edits retain previous values in revisions; reports use corrected canonical expense values. There is no new frozen annual-report issuance/versioning workflow.
- Supporting documents use the existing validated private-file architecture, not public static links. Up to five preserved documents per expense are supported.
- Legacy daily cashbook routes remain available; the new Cash Books service provides the full historical opening/closing and correction-date reporting convention.
- Automated PDF validation is included; no manual screenshot or pixel-matching review is claimed.
- The build's existing static/dynamic import overlap and main bundle-size advisories remain non-blocking.
- The application database's pending prerequisite and new migrations remain unapplied.

## 22. Inferred templates and references

The monthly reference image was not attached, so its written income/expenditure/summary/notes structure is used. No final images were supplied for Cash Book, Cash Received, Annual or Expense reports; these use conventional accounting rows, subtotals, balances, dates and references.

Layout research used the [Charity Commission receipts/payments template](https://www.gov.uk/government/publications/receipts-and-payments-accounts-cc16-charity-accounting-template) and the [Department for Education income/expenditure reporting framework](https://www.gov.uk/guidance/consistent-financial-reporting-framework-2026-to-2027) as structural inspiration only. No institution branding or proprietary wording was copied, and no external jurisdiction's accounting rules were adopted as MTM policy.
