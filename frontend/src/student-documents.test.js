import assert from 'node:assert/strict'
import { test, afterEach } from 'node:test'
import { readFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import { Buffer } from 'node:buffer'
import React from 'react'
import { JSDOM } from 'jsdom'
import { transformWithOxc } from 'vite'

const dom = new JSDOM('<html><body></body></html>', { url: 'http://localhost/' })
globalThis.window = dom.window; globalThis.document = dom.window.document
globalThis.HTMLElement = dom.window.HTMLElement; globalThis.Element = dom.window.Element
globalThis.IS_REACT_ACT_ENVIRONMENT = true
const { render, screen, fireEvent, cleanup, waitFor } = await import('@testing-library/react')
const require = createRequire(import.meta.url)
let params = { studentId: '7' }, requests = [], downloads = []
let handler = async () => []
const mocks = {
  'react-router-dom': { useParams: () => params, Link: ({ to, children, ...props }) => React.createElement('a', { href: to, ...props }, children) },
  '../api/client': { apiClient: async (...args) => { requests.push(args); return handler(...args) }, apiDownload: async (...args) => { downloads.push(args) } },
  '../components/StudentPicker': { default: ({ onChange }) => React.createElement('button', { onClick: () => onChange({ id: 7, display_name: 'Alice Learner' }) }, 'Choose Alice') },
}
globalThis.studentDocumentMocks = mocks
const dataUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const cache = new Map()
async function compile(url) {
  if (cache.has(url.href)) return cache.get(url.href)
  let code = (await transformWithOxc(await readFile(url, 'utf8'), url.pathname, { jsx: { runtime: 'automatic' } })).code
  for (const match of [...code.matchAll(/from (["'])([^"']+)\1/g)]) {
    const specifier = match[2]
    let resolved
    if (mocks[specifier]) resolved = dataUrl(Object.keys(mocks[specifier]).map(key => key === 'default' ? `export default globalThis.studentDocumentMocks[${JSON.stringify(specifier)}].default;` : `export const ${key}=globalThis.studentDocumentMocks[${JSON.stringify(specifier)}][${JSON.stringify(key)}];`).join('\n'))
    else if (specifier.startsWith('.')) {
      let relative = new URL(specifier, url)
      if (!/\.(jsx|js)$/.test(specifier)) relative = new URL(specifier + (existsSync(new URL(specifier + '.jsx', url)) ? '.jsx' : '.js'), url)
      resolved = relative.pathname.endsWith('.jsx') ? await compile(relative) : relative.href
    } else resolved = pathToFileURL(require.resolve(specifier)).href
    code = code.replace(match[0], `from ${JSON.stringify(resolved)}`)
  }
  const result = dataUrl(code); cache.set(url.href, result); return result
}
const load = async path => (await import(await compile(new URL(path, import.meta.url)))).default
const Nav = await load('./components/StudentFeeNavigation.jsx')
const Debtors = await load('./pages/DebtorsPage.jsx')
const Invoices = await load('./pages/InvoicesPage.jsx')
const Statement = await load('./pages/AccountStatementPage.jsx')
const History = await load('./pages/AcademicHistoryPage.jsx')
const Settings = await load('./components/DocumentSettingsPanel.jsx')
afterEach(() => { cleanup(); requests = []; downloads = []; params = { studentId: '7' } })

const school = { name: 'School A', address: 'School Road', phone: '123', email: 'school@example.test', brand_color: '#244768' }
const years = [{ id: 1, name: '2026' }], terms = [{ id: 1, name: 'Term 1', academic_year: 1 }]
const student = { id: 7, name: 'Alice Learner', admission_number: 'A-001', class_name: 'Grade 2', guardian: 'Guardian' }
const debtor = { student: 7, student_name: student.name, admission_number: student.admission_number, class_name: student.class_name, guardian: student.guardian,
  charges: 100, payments: 25, adjustments: 0, outstanding: 75, not_due: 0, days_0_30: 0, days_31_60: 75, days_61_90: 0, days_90_plus: 0 }
const report = { school, currency: 'USD', years, terms, classes: [{ id: 2, name: 'Grade 2' }], reporting_date: '2026-10-16', rows: [debtor], totals: debtor, note: 'Due-date ageing' }
const invoice = { id: 1, number: 'INV-000001', school, student, academic_year: '2026', academic_year_id: 1, term: 'Term 1', term_id: 1, issued_on: '2026-10-16', due_date: '2026-10-31', currency: 'USD', lines: [{ quantity: 1, description: 'Tuition', unit_amount: '100', total: '100' }], subtotal: 100, total: 100, payments_allocated: 25, outstanding_balance: 75, total_amount_due: 75, payment_status: 'Part paid' }

test('Student Fee Management navigation exposes all eight sections', () => {
  render(React.createElement(Nav))
  for (const [name, path] of [['Fee Structures', 'fee-management'], ['Student Charges', 'charges'], ['Payments', 'payments'], ['Receipts', 'receipts'], ['Invoices', 'invoices'], ['Student Financial Statements', 'statements'], ['Outstanding Balances', 'outstanding'], ['Ageing Debtors', 'ageing']]) {
    assert.equal(screen.getByRole('link', { name }).getAttribute('href'), `/school/finance/${path}`)
  }
})

test('Ageing Debtors filters, server sorting, header sorting and exports', async () => {
  handler = async () => report
  render(React.createElement(Debtors))
  await screen.findByText('Alice Learner')
  for (const [label, value] of [['Academic Year', '1'], ['Term', '1'], ['Class / Grade', '2'], ['Reporting Date', '2026-10-16'], ['Search student', 'Alice'], ['Sort by', '-outstanding']]) fireEvent.change(screen.getByLabelText(label), { target: { value } })
  await waitFor(() => assert.match(requests.at(-1)[0], /sort=-outstanding/))
  assert.match(requests.at(-1)[0], /school_class=2/); assert.match(requests.at(-1)[0], /reporting_date=2026-10-16/)
  fireEvent.click(screen.getByRole('button', { name: 'Student Name' }))
  await waitFor(() => assert.equal(screen.getByRole('columnheader', { name: /Student Name/ }).getAttribute('aria-sort'), 'ascending'))
  fireEvent.click(screen.getByRole('button', { name: 'Export PDF' })); fireEvent.click(screen.getByRole('button', { name: 'Export Excel' }))
  assert.match(downloads[0][0], /school\/finance\/ageing\/.*export=pdf/)
  assert.match(downloads[1][0], /term=1.*export=xlsx/)
  assert.ok(screen.getByText('School totals for selected filters'))
})

test('Outstanding Balances exposes charges, actual payments and outstanding separately', async () => {
  handler = async () => report
  render(React.createElement(Debtors, { outstanding: true }))
  await screen.findByText('Alice Learner')
  assert.match(requests[0][0], /finance\/outstanding/)
  assert.ok(screen.getByRole('columnheader', { name: 'Charges' })); assert.ok(screen.getByRole('columnheader', { name: 'Payments' }))
  assert.ok(screen.getByRole('columnheader', { name: 'Outstanding Balance' }))
})

test('invoice generation uses an existing student charge and lists the official document', async () => {
  handler = async (path, options) => options?.method === 'POST' ? invoice : path.includes('fee-assignments') ? [{ id: 9, student: 7, fee_name: 'Tuition', currency: 'USD', amount_owed: 100 }] : []
  render(React.createElement(Invoices))
  fireEvent.click(screen.getByRole('button', { name: 'Choose Alice' }))
  await screen.findByRole('option', { name: /Tuition/ })
  fireEvent.change(screen.getByLabelText('Billed charge'), { target: { value: '9' } })
  fireEvent.click(screen.getByRole('button', { name: 'Generate Invoice' }))
  await screen.findByRole('link', { name: 'INV-000001' })
  const mutation = requests.find(([, options]) => options?.method === 'POST')
  assert.deepEqual(JSON.parse(mutation[1].body), { assignment: 9 })
  fireEvent.change(screen.getByLabelText('Search invoice or student'), { target: { value: 'missing' } })
  assert.ok(screen.getByText('No invoices match this selection.'))
})

test('invoice detail is branded and supports PDF and print', async () => {
  params = { invoiceId: '1' }; handler = async () => invoice
  let printed = false; window.print = () => { printed = true }
  render(React.createElement(Invoices))
  await screen.findByText('Invoice No. INV-000001')
  assert.ok(screen.getByText('School A')); assert.ok(screen.getByText('Payments Allocated'))
  fireEvent.click(screen.getByRole('button', { name: 'Download PDF' }))
  assert.equal(downloads[0][0], '/school/finance/invoices/1/?export=pdf')
  fireEvent.click(screen.getByRole('button', { name: 'Print Invoice' })); assert.equal(printed, true)
})

test('parent invoice UI is read only and handles disabled access', async () => {
  handler = async () => [invoice]
  const view = render(React.createElement(Invoices, { parent: true }))
  await screen.findByRole('link', { name: 'INV-000001' })
  assert.equal(screen.queryByRole('button', { name: 'Generate Invoice' }), null)
  assert.equal(screen.queryByRole('navigation', { name: 'Student Fee Management' }), null)
  assert.equal(requests[0][0], '/parent/invoices/')
  view.unmount()
  handler = async () => { throw Object.assign(new Error('Denied'), { status: 403 }) }
  render(React.createElement(Invoices, { parent: true }))
  await screen.findByRole('alert'); assert.match(screen.getByRole('alert').textContent, /not enabled/)
})

test('statement filters preserve original transaction order, totals and export parameters', async () => {
  handler = async () => ({ school, student, currency: 'USD', years, terms, generated_at: '2026-10-16', period: { start: '2026-02-01', end: '2026-02-28' }, summary: { opening_balance: 100, charges: 0, payments: 25, adjustments_reversals: 0, closing_balance: 75 }, transactions: [{ date: '2026-02-10', reference: 'R-001', period: '2025 / Term 3', description: 'Payment: Tuition', debit: 0, credit: 25, balance: 75 }] })
  render(React.createElement(Statement, { parent: true }))
  await screen.findByText('Payment: Tuition')
  for (const [label, value] of [['Academic Year', '1'], ['Term', '1'], ['From', '2026-02-01'], ['To', '2026-02-28']]) fireEvent.change(screen.getByLabelText(label), { target: { value } })
  await waitFor(() => assert.match(requests.at(-1)[0], /date_to=2026-02-28/))
  await waitFor(() => assert.equal(screen.getByRole('button', { name: 'Export Excel' }).disabled, false))
  assert.equal(screen.queryByRole('button', { name: 'Running Balance' }), null)
  fireEvent.click(screen.getByRole('button', { name: 'Export Excel' }))
  assert.match(downloads[0][0], /parent\/students\/7\/statement\/.*academic_year=1.*term=1.*date_from=2026-02-01.*export=xlsx/)
  fireEvent.click(screen.getByRole('button', { name: 'Download PDF' })); assert.match(downloads[1][0], /export=pdf/)
  fireEvent.click(screen.getByRole('button', { name: 'All history' }))
  await waitFor(() => assert.equal(requests.at(-1)[0], '/parent/students/7/statement/?'))
})

test('academic history displays preserved official grade and published comments', async () => {
  handler = async () => ({ school, student, years, note: 'Published records only', periods: [{ report_card: 1, academic_year: '2025', academic_year_id: 1, term: 'Term 1', term_id: 1, class_name: 'Former Grade', version: 1, comments: ['Official school comment'], results: [{ id: 1, subject: 'Mathematics', score: '80', maximum_score: '100', percentage: '80', grade: 'Historic A', comment: 'Official subject comment' }] }] })
  render(React.createElement(History, { parent: true }))
  await screen.findByText('Historic A'); assert.ok(screen.getByText('Official subject comment'))
  assert.ok(screen.getByText(/Former Grade/))
  fireEvent.click(screen.getByRole('button', { name: 'Download PDF' }))
  assert.match(downloads[0][0], /parent\/students\/7\/academic-history\/.*export=pdf/)
})

test('document settings explicitly control parent invoice access and future grading', async () => {
  handler = async (path, options) => options?.method === 'PATCH' ? JSON.parse(options.body) : { motto: '', website: '', additional_contacts: '', contact_person: '', brand_color: '#244768', parent_invoice_access: false, grading_scale: [] }
  render(React.createElement(Settings))
  const enabled = await screen.findByRole('checkbox', { name: /Enable Parent Portal/ })
  assert.equal(enabled.checked, false)
  fireEvent.click(enabled); fireEvent.click(screen.getByRole('button', { name: 'Save Document Settings' }))
  await screen.findByText('Document settings saved.')
  assert.equal(JSON.parse(requests.at(-1)[1].body).parent_invoice_access, true)
})

test('changed debtor filters cannot print or export stale figures while loading', async () => {
  let resolveReport
  handler = async path => path.includes('reporting_date=2026-10-01') ? new Promise(resolve => { resolveReport = resolve }) : report
  render(React.createElement(Debtors))
  await screen.findByText('Alice Learner')
  fireEvent.change(screen.getByLabelText('Reporting Date'), { target: { value: '2026-10-01' } })
  await waitFor(() => assert.equal(typeof resolveReport, 'function'))
  assert.equal(screen.getByRole('button', { name: 'Export PDF' }).disabled, true)
  assert.equal(screen.getByRole('button', { name: 'Print' }).disabled, true)
  assert.equal(screen.queryByText('Alice Learner'), null)
  fireEvent.click(screen.getByRole('button', { name: 'Export PDF' })); assert.equal(downloads.length, 0)
  resolveReport({ ...report, reporting_date: '2026-10-01' })
  await screen.findByText('Alice Learner')
  assert.equal(screen.getByRole('button', { name: 'Export PDF' }).disabled, false)
})
