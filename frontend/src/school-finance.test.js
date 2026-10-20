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
const { render, screen, fireEvent, cleanup, waitFor, within } = await import('@testing-library/react')
const require = createRequire(import.meta.url)
let requests = [], downloads = [], handler
const mocks = {
  'react-router-dom': { Link: ({ to, children, ...props }) => React.createElement('a', { href: to, ...props }, children) },
  '../api/client': { apiClient: async (...args) => { requests.push(args); return handler(...args) }, apiDownload: async (...args) => { downloads.push(args) } },
  '../components/StudentPicker': { default: ({ onChange }) => React.createElement('button', { onClick: () => onChange({ id: 7, display_name: 'Alice' }) }, 'Choose Alice') },
}
globalThis.schoolFinanceMocks = mocks
const dataUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const cache = new Map()
async function compile(url) {
  if (cache.has(url.href)) return cache.get(url.href)
  let code = (await transformWithOxc(await readFile(url, 'utf8'), url.pathname, { jsx: { runtime: 'automatic' } })).code
  for (const match of [...code.matchAll(/from (["'])([^"']+)\1/g)]) {
    const specifier = match[2]
    let resolved
    if (mocks[specifier]) resolved = dataUrl(Object.keys(mocks[specifier]).map(key => key === 'default' ? `export default globalThis.schoolFinanceMocks[${JSON.stringify(specifier)}].default;` : `export const ${key}=globalThis.schoolFinanceMocks[${JSON.stringify(specifier)}][${JSON.stringify(key)}];`).join('\n'))
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
const Finance = await load('./pages/FinancePage.jsx')
const Reports = await load('./pages/SchoolFinancialPage.jsx')
const Entry = await load('./components/FinancialEntryForm.jsx')
const Expenses = await load('./pages/SchoolExpensesPage.jsx')
const Configuration = await load('./pages/FinanceConfigurationPage.jsx')
const PaymentFields = await load('./components/PaymentClassificationFields.jsx')
afterEach(() => { cleanup(); requests = []; downloads = []; window.history.replaceState({}, '', '/') })

const school = { name: 'School A', address: 'School Road', phone: '123', email: 'school@example.test', brand_color: '#244768' }
const lookups = { accounts: [{ id: 1, name: 'Main Cash', kind: 'cash', is_active: true }], categories: [{ id: 2, name: 'Donations', kind: 'income', is_active: true }, { id: 3, name: 'Cleaning', kind: 'expense', is_active: true }], expense_categories: [{ id: 'utilities', name: 'Utilities' }, { id: 'other', name: 'Other' }], currency: 'USD',
  years: [{ id: 1, name: '2026', start_date: '2026-01-01' }], terms: [{ id: 1, name: 'Term 1', academic_year: 1 }], classes: [{ id: 1, name: 'Grade 2' }], payment_methods: ['cash', 'bank'] }
const common = { school, currency: 'USD', generated_at: '2026-01-31T12:00:00Z', period: { start: '2026-01-01', end: '2026-01-31' }, note: 'Recorded cash-basis history', notes: '' }
const monthly = { ...common, title: 'Monthly Financial Report', summary: { billed_fees: 100, fees_collected: 25, cash_collected: 25, other_income: 20, total_cash_income: 45, expenses: 10, surplus_deficit: 35, outstanding_receivables: 75 }, budget_configured: false,
  categories: [{ section: 'income', category_key: 'income:fees', category: 'School Fee Payments', actual: 25 }, { section: 'expenditure', category_key: 'expense:utilities', category: 'Utilities', actual: 10 }], months: [{ month: '2026-01', billed_fees: 100, fees_collected: 25, other_income: 20, expenses: 10, surplus_deficit: 35 }] }
const movement = { ...common, title: 'Cash Book', summary: { opening_balance: 0, money_in: 25, money_out: 0, closing_balance: 25, net_movement: 25 }, method_totals: { cash: 25 },
  rows: [{ id: 'payment:8', date: '2026-01-15', reference: 'PAY-8', source: 'Student payment', category: 'School Fee Payments', description: 'Tuition', student_name: 'Alice', admission_number: 'A001', class_name: 'Previous Grade', student: 7, money_in: 25, money_out: 0, amount: 25, balance: 25, payment_method: 'cash', account_name: 'Main Cash', received_by: 'Administrator', linked_type: 'payment', linked_id: 8, receipt: 9, receipt_number: 'RCPT-9', status: 'Valid' }] }
const expense = { id: 4, expense_date: '2026-01-20', category: 'utilities', description: 'Water supplier bill', amount: '10', payment_method: 'cash', account: 1, payee: 'Water supplier', reference: 'W-1', notes: 'Paid', is_reversed: false, recorded_by_name: 'Administrator', created_at: '2026-01-20', updated_at: '2026-01-20', attachments: [{ id: 5, name: 'bill.pdf', download_url: '/school/expenses/4/attachments/5/download/' }] }

test('Finance separates student fees and school-wide finance and marks reconciliation FUTURE', () => {
  render(React.createElement(Finance))
  for (const title of ['Student Fee Management', 'School Financial Management']) assert.ok(screen.getByRole('heading', { name: title }))
  for (const [name, path] of [['Income Records', 'income'], ['Expenses', 'expenses'], ['Cash Books', 'cash-books'], ['Monthly Financial Reports', 'monthly'], ['Annual Financial Reports', 'annual'], ['Financial Dashboard', 'financial-dashboard']]) assert.equal(screen.getByRole('link', { name }).getAttribute('href'), `/school/finance/${path}`)
  assert.ok(screen.getByText('Bank Reconciliation = FUTURE'))
  assert.equal(screen.queryByRole('link', { name: /Bank Reconciliation/ }), null)
})

test('monthly dashboard distinguishes billed fees, collected cash, income, expenses and receivables without fictitious budgets', async () => {
  handler = async path => path.includes('lookups') ? lookups : monthly
  render(React.createElement(Reports, { report: 'monthly' }))
  await screen.findByText('School A')
  for (const label of ['Billed Fees', 'Cash Collected from Student Payments', 'Other Income', 'Total Cash Income', 'Operating Expenses', 'Operating Surplus / Deficit', 'Outstanding Receivables at Period End']) assert.ok(screen.getAllByText(label).length)
  assert.equal(screen.queryByRole('columnheader', { name: 'Budget' }), null)
  assert.equal(screen.queryByRole('columnheader', { name: 'Variance' }), null)
  fireEvent.change(screen.getByLabelText('Month'), { target: { value: '2' } })
  await waitFor(() => assert.match(requests.at(-1)[0], /month=2/))
  await screen.findByText('School A')
  fireEvent.change(screen.getByLabelText('Management Notes'), { target: { value: 'Material expense explanation.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save Report Notes' }))
  await screen.findByText('Report notes saved.')
  const save = requests.find(([, options]) => options?.method === 'POST')
  assert.deepEqual(JSON.parse(save[1].body), { start_date: common.period.start, end_date: common.period.end, body: 'Material expense explanation.' })
})

test('cashbook filters, historical class, sort, protected exports, receipt and print', async () => {
  handler = async path => path.includes('lookups') ? lookups : movement
  let printed = false; window.print = () => { printed = true }
  render(React.createElement(Reports, { report: 'cash-books' }))
  await screen.findByText('Tuition')
  for (const [label, value] of [['Reporting Period', 'custom'], ['From', '2026-01-01'], ['To', '2026-01-31'], ['Account', '1'], ['Category', 'income:fees'], ['Payment Method', 'cash'], ['Class / Grade', '1'], ['Search', 'Tuition']]) fireEvent.change(screen.getByLabelText(label), { target: { value } })
  await screen.findByText('Tuition')
  fireEvent.click(screen.getByRole('button', { name: 'Money In', exact: true }))
  await screen.findByText('Tuition')
  assert.match(requests.at(-1)[0], /account=1/); assert.match(requests.at(-1)[0], /school_class=1/)
  fireEvent.click(screen.getByRole('button', { name: 'Export PDF' })); fireEvent.click(screen.getByRole('button', { name: 'Export Excel' }))
  assert.match(downloads[0][0], /cash-books\/.*start_date=2026-01-01.*export=pdf/)
  assert.match(downloads[1][0], /export=xlsx/)
  fireEvent.click(screen.getByRole('button', { name: 'Receipt', exact: true })); assert.equal(downloads[2][0], '/school/receipts/9/pdf/')
  fireEvent.click(screen.getByRole('button', { name: 'Print Report' })); assert.equal(printed, true)
})

test('annual report selects academic year and exports the selected scope', async () => {
  handler = async path => path.includes('lookups') ? lookups : { ...monthly, title: 'Annual Financial Report' }
  render(React.createElement(Reports, { report: 'annual' }))
  await screen.findByText('School A')
  fireEvent.change(screen.getByLabelText('Academic Year'), { target: { value: '1' } })
  await screen.findByText('School A')
  assert.match(requests.at(-1)[0], /annual\/.*academic_year=1/)
  fireEvent.click(screen.getByRole('button', { name: 'Export Excel' }))
  assert.match(downloads[0][0], /annual\/.*academic_year=1.*export=xlsx/)
  assert.equal(screen.queryByLabelText('Term'), null)
})

test('manual non-student income uses canonical endpoint and retains operation key across a failed retry', async () => {
  let attempts = 0, saved
  handler = async (path, options) => { if (++attempts === 1) throw new Error('Connection lost'); return { id: 10, ...JSON.parse(options.body) } }
  render(React.createElement(Entry, { lookups, onSaved: value => { saved = value } }))
  for (const [label, value] of [['Source', 'Community'], ['Description', 'Donation'], ['Amount (USD)', '20.25'], ['Reference', 'DON-1']]) fireEvent.change(screen.getByLabelText(label), { target: { value } })
  fireEvent.click(screen.getByRole('button', { name: 'Save Other Income' }))
  await screen.findByRole('alert')
  fireEvent.click(screen.getByRole('button', { name: 'Save Other Income' }))
  await waitFor(() => assert.equal(saved.amount, '20.25'))
  assert.equal(requests[0][0], '/school/finance/other-income/')
  assert.equal(requests[0][1].headers['Idempotency-Key'], requests[1][1].headers['Idempotency-Key'])
  assert.equal('student' in JSON.parse(requests[0][1].body), false)
})

test('expense edits preserve canonical identity and support payee, account, category and protected documents', async () => {
  let savedExpense = { ...expense }, listRequests = 0, releaseRefresh
  handler = async (path, options) => {
    if (path === '/school/finance/lookups/') return lookups
    if (path === '/school/expenses/4/' && options?.method === 'PATCH') {
      savedExpense = { ...savedExpense, ...JSON.parse(options.body) }
      return savedExpense
    }
    if (path === '/school/expenses/?') {
      if (++listRequests === 1) return [savedExpense]
      return new Promise(resolve => { releaseRefresh = () => resolve([savedExpense]) })
    }
    throw new Error(`Unexpected expense request: ${path}`)
  }
  render(React.createElement(Expenses))
  const originalRow = (await screen.findByRole('button', { name: 'bill.pdf' })).closest('tr')
  assert.ok(within(originalRow).getByText('Water supplier bill'))
  fireEvent.click(within(originalRow).getByRole('button', { name: 'Edit Expense' }))
  fireEvent.change(screen.getByLabelText('Amount (USD)'), { target: { value: '12.50' } })
  fireEvent.change(screen.getByLabelText('Supplier / Payee'), { target: { value: 'Verified supplier' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }))
  await screen.findByText(/Expense saved/)
  const mutation = requests.find(([, options]) => options?.method === 'PATCH')
  assert.equal(mutation[0], '/school/expenses/4/')
  assert.equal(JSON.parse(mutation[1].body).payee, 'Verified supplier')
  // Saving starts a separate list refresh; the notice does not mean it has finished.
  await waitFor(() => assert.equal(typeof releaseRefresh, 'function'))
  assert.equal(listRequests, 2)
  assert.equal(screen.queryByRole('table'), null)
  assert.equal(screen.getByRole('button', { name: 'Export PDF' }).disabled, true)
  releaseRefresh()
  const attachment = await screen.findByRole('button', { name: 'bill.pdf' })
  const refreshedRow = attachment.closest('tr')
  assert.ok(within(refreshedRow).getByText('Water supplier bill'))
  assert.ok(within(refreshedRow).getByText('Verified supplier'))
  assert.ok(within(refreshedRow).getByText('USD 12.50'))
  assert.equal(screen.getByRole('button', { name: 'Export PDF' }).disabled, false)
  fireEvent.click(attachment)
  assert.deepEqual(downloads, [['/school/expenses/4/attachments/5/download/', 'bill.pdf']])
})

test('account and category configuration is school-scoped and deactivates rather than deletes', async () => {
  handler = async path => path.includes('lookups') ? lookups : {}
  render(React.createElement(Configuration))
  await screen.findByRole('button', { name: 'Deactivate Main Cash' })
  fireEvent.click(screen.getByRole('button', { name: 'Deactivate Main Cash' }))
  await waitFor(() => assert.ok(requests.some(([path, options]) => path === '/school/finance/accounts/1/' && options?.method === 'PATCH')))
  assert.equal(requests.some(([, options]) => options?.method === 'DELETE'), false)
})

test('payment form selects an existing school account and income category', async () => {
  handler = async () => lookups
  const changes = []
  render(React.createElement(PaymentFields, { onChange: (...args) => changes.push(args) }))
  await screen.findByRole('option', { name: 'Main Cash' })
  fireEvent.change(screen.getByLabelText('Cash / Bank Account'), { target: { value: '1' } })
  fireEvent.change(screen.getByLabelText('Income Category'), { target: { value: '2' } })
  assert.deepEqual(changes, [['account', 1], ['income_category', 2]])
})

test('school-wide report handles permission rejection without displaying finance data', async () => {
  handler = async path => { if (path.includes('lookups')) return lookups; throw Object.assign(new Error('Denied'), { data: { detail: 'A school administrator account is required.' } }) }
  render(React.createElement(Reports))
  await screen.findByRole('alert')
  assert.equal(screen.queryByText('School A'), null)
  assert.equal(screen.getByRole('button', { name: 'Export PDF' }).disabled, true)
})

test('period changes hide stale financial cards and disable exports until loaded', async () => {
  let release
  handler = async path => path.includes('lookups') ? lookups : path.includes('month=2') ? new Promise(resolve => { release = resolve }) : monthly
  render(React.createElement(Reports, { report: 'monthly' }))
  await screen.findByText('School A')
  // Force a different month regardless of the execution date.
  fireEvent.change(screen.getByLabelText('Month'), { target: { value: '1' } })
  await screen.findByText('School A')
  fireEvent.change(screen.getByLabelText('Month'), { target: { value: '2' } })
  await waitFor(() => assert.equal(typeof release, 'function'))
  assert.equal(screen.queryByText('Total Cash Income'), null)
  assert.equal(screen.getByRole('button', { name: 'Export PDF' }).disabled, true)
  release(monthly)
  await screen.findByText('School A')
  assert.equal(screen.getByRole('button', { name: 'Export PDF' }).disabled, false)
})

test('expense report links preserve the selected dates and account', async () => {
  handler = async path => path.includes('lookups') ? lookups : [expense]
  render(React.createElement(Expenses))
  await screen.findByText('Water supplier bill')
  fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-01-01' } })
  fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-01-31' } })
  fireEvent.change(screen.getByLabelText('Filter Account'), { target: { value: '1' } })
  const link = await screen.findByRole('link', { name: 'Print / View Expense Report' })
  assert.match(link.getAttribute('href'), /start_date=2026-01-01.*end_date=2026-01-31.*account=1/)
})

test('shared report URL restores its date range and transaction filters', async () => {
  window.history.replaceState({}, '', '/school/finance/expense-report?period=custom&start_date=2026-01-01&end_date=2026-01-31&account=1')
  handler = async path => path.includes('lookups') ? lookups : movement
  render(React.createElement(Reports, { report: 'expense-report' }))
  await screen.findByText('Tuition')
  assert.equal(screen.getByLabelText('From').value, '2026-01-01')
  assert.equal(screen.getByLabelText('Account').value, '1')
  assert.match(requests.find(([path]) => path.includes('reports/'))[0], /period=custom.*account=1/)
})
