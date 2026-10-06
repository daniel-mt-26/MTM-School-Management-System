import 'fake-indexeddb/auto'
import assert from 'node:assert/strict'
import { after, afterEach, test } from 'node:test'
import React from 'react'
import { JSDOM } from 'jsdom'
import { transformWithOxc } from 'vite'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import { Buffer } from 'node:buffer'
import { OfflineContext } from './offline/context.js'
import { queuedOperations, clearOfflineScope } from './offline/db.js'
import { cacheAttendanceLookups, cachedAttendanceLookups, cacheAttendanceRoster } from './offline/attendance.js'

const dom = new JSDOM('<html><body></body></html>', { url: 'http://localhost' })
globalThis.window = dom.window
globalThis.document = dom.window.document
globalThis.HTMLElement = dom.window.HTMLElement
globalThis.IS_REACT_ACT_ENVIRONMENT = true
const { render, fireEvent, screen, waitFor, within, cleanup } = await import('@testing-library/react')
const require = createRequire(import.meta.url)
const moduleCache = new Map()
const mocks = {
  'react-router-dom': { useParams: () => ({ studentId: '1' }), Link: ({ to, children, ...props }) => React.createElement('a', { href: to, ...props }, children) },
  '../offline/context': { OfflineContext },
  '../api/client': { apiClient: (...args) => apiMock(...args) },
  '../api/students': { getStudents: async () => [] },
  '../api/finance': { getFinanceRecords: async (resource) => financeData[resource] || [], saveFinanceRecord: (...args) => saveFeeMock(...args) },
  '../api/academics': { getAcademicRecords: (resource) => academicMock(resource), saveAcademicRecord: (...args) => subjectSaveMock(...args) },
  '../api/attendance': { getAttendanceRoster: async (context) => { rosterRequests++; return { ...roster, ...context } }, saveAttendanceBulk: async (payload) => { saved.push(payload); return { roster: { ...roster, ...payload, students: roster.students.map((s) => ({ ...s, attendance: payload.entries.find((e) => e.enrollment === s.enrollment) })) } } } },
}
globalThis.academicsTestMocks = mocks
const dataUrl = (code) => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
async function compile(url) {
  if (moduleCache.has(url.href)) return moduleCache.get(url.href)
  const source = await readFile(url, 'utf8')
  const transformed = await transformWithOxc(source, url.pathname, { jsx: { runtime: 'automatic' } })
  let code = transformed.code
  for (const match of [...code.matchAll(/from (["'])([^"']+)\1/g)]) {
    const specifier = match[2]
    let resolved
    if (mocks[specifier]) {
      resolved = dataUrl(Object.keys(mocks[specifier]).map((key) => `export const ${key} = globalThis.academicsTestMocks[${JSON.stringify(specifier)}][${JSON.stringify(key)}];`).join('\n'))
    } else if (specifier.startsWith('.')) {
      const relative = new URL(/\.(js|jsx)$/.test(specifier) ? specifier : specifier + (specifier.includes('components/') || specifier === './SubjectPicker' ? '.jsx' : '.js'), url)
      resolved = relative.pathname.endsWith('.jsx') ? await compile(relative) : relative.href
    } else resolved = pathToFileURL(require.resolve(specifier)).href
    code = code.replace(match[0], `from ${JSON.stringify(resolved)}`)
  }
  const result = dataUrl(code)
  moduleCache.set(url.href, result)
  return result
}
const { default: SubjectPicker } = await import(await compile(new URL('./components/SubjectPicker.jsx', import.meta.url)))
const { default: FeeManagementPage } = await import(await compile(new URL('./pages/FeeManagementPage.jsx', import.meta.url)))
const { default: AccountStatementPage } = await import(await compile(new URL('./pages/AccountStatementPage.jsx', import.meta.url)))
const { default: TimetablesPage } = await import(await compile(new URL('./pages/TimetablesPage.jsx', import.meta.url)))
const { default: AttendancePage } = await import(await compile(new URL('./pages/AttendancePage.jsx', import.meta.url)))
const { default: AcademicsPage } = await import(await compile(new URL('./pages/AcademicsPage.jsx', import.meta.url)))
const { default: TimetableEditor } = await import(await compile(new URL('./components/TimetableEditor.jsx', import.meta.url)))
afterEach(cleanup)
after(() => dom.window.close())
const today = new Date()
const date = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
const classes = [{ id: 1, name: 'Grade 3', is_active: true }, { id: 2, name: 'Grade 4', is_active: true }]
const years = [{ id: 1, name: 'Current year', is_current: true }]
const terms = [{ id: 1, name: 'Term 1', academic_year: 1, start_date: '2020-01-01', end_date: '2030-12-31' }]
const roster = { school_class: 1, class_name: 'Grade 3', academic_year: 1, academic_year_name: 'Current year', term: 1, term_name: 'Term 1', attendance_date: date, students: [{ enrollment: 11, display_name: 'Tariro Moyo', admission_number: '001', attendance: null }, { enrollment: 12, display_name: 'Tanaka Ncube', admission_number: '002', attendance: null }] }
let rosterRequests = 0
let saved = []
let apiMock = async () => ({ records: [], summary: { present: 0, absent: 0, late: 0, excused: 0 } })
let academicMock = async (resource) => ({ classes, 'academic-years': years, terms, 'subjects/library': { groups: [], activities: ['Break'] } })[resource]
const financeData = { 'academic-years': years, terms, classes }
let subjectSaveMock = async () => []
let saveFeeMock = async () => ({ id: 7, is_active: false })

test('dashboard retains Attendance and Timetables without duplicate subject cards', () => {
  render(React.createElement(AcademicsPage))
  assert.ok(screen.getByRole('heading', { name: 'Attendance' }))
  assert.ok(screen.getByRole('heading', { name: 'Timetables' }))
  assert.equal(Boolean(screen.queryByRole('heading', { name: 'Subjects' })), false)
  assert.equal(Boolean(screen.queryByRole('heading', { name: 'Class Subjects' })), false)
})

test('timetable class selection, active subjects, activities and conflict explanations', () => {
  let current
  function Editor() {
    const [form, setForm] = React.useState({ name: 'Shared', academic_year: '1', term: '1', classes: [1], entries: [{ day_of_week: 'Monday', start_time: '08:00', end_time: '08:30', subject: 1, label: '' }] })
    current = form
    return React.createElement(TimetableEditor, { form, setForm, lookups: { classes, years, terms, activities: ['Assembly', 'Break'], subjects: [{ id: 1, name: 'Mathematics', is_active: true }, { id: 2, name: 'Inactive subject', is_active: false }] }, onSave: (e) => e.preventDefault(), error: 'Grade 4: Monday conflicts with 08:00–08:30.' })
  }
  render(React.createElement(Editor))
  assert.equal(screen.getByLabelText('Grade 3').checked, true)
  fireEvent.click(screen.getByLabelText('Grade 4'))
  assert.deepEqual(current.classes, [1, 2])
  assert.equal(Boolean(screen.queryByRole('option', { name: 'Inactive subject' })), false)
  assert.equal(screen.getByRole('combobox', { name: 'Subject' }).value, 'Mathematics')
  fireEvent.change(screen.getByLabelText('Entry Type'), { target: { value: 'activity' } })
  fireEvent.change(screen.getByLabelText('Activity'), { target: { value: 'Break' } })
  assert.equal(current.entries[0].subject, null)
  assert.equal(current.entries[0].label, 'Break')
  assert.match(screen.getByRole('alert').textContent, /Grade 4/)
})

test('attendance starts with classes, marks exceptions, then submits one full roster', async () => {
  rosterRequests = 0; saved = []
  const scope = `academics-online:${crypto.randomUUID()}`
  render(React.createElement(OfflineContext.Provider, { value: { scope, isReachable: true } }, React.createElement(AttendancePage)))
  await screen.findByRole('button', { name: 'Grade 3' })
  assert.equal(rosterRequests, 0)
  assert.equal(Boolean(screen.queryByRole('button', { name: 'Save Attendance' })), false)
  fireEvent.click(screen.getByRole('button', { name: 'Grade 3' }))
  await screen.findByRole('button', { name: 'Mark All Present' })
  fireEvent.click(screen.getByRole('button', { name: 'Mark All Present' }))
  assert.equal(saved.length, 0)
  fireEvent.click(within(screen.getByRole('group', { name: 'Attendance for Tariro Moyo' })).getByRole('button', { name: 'Absent' }))
  fireEvent.click(screen.getByRole('button', { name: 'Save Attendance' }))
  await waitFor(() => assert.equal(saved.length, 1))
  assert.deepEqual(saved[0].entries.map((x) => [x.enrollment, x.status]), [[11, 'absent'], [12, 'present']])
  await clearOfflineScope(scope)
})

test('offline class list and roster remain tenant-scoped and queue a bulk save', async () => {
  const scope = `academics-offline:${crypto.randomUUID()}`
  await cacheAttendanceLookups(scope, { classes, years, terms })
  await cacheAttendanceRoster(scope, roster)
  assert.equal(await cachedAttendanceLookups('another-school'), null)
  render(React.createElement(OfflineContext.Provider, { value: { scope, isReachable: false } }, React.createElement(AttendancePage)))
  fireEvent.click(await screen.findByRole('button', { name: 'Grade 3' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Mark All Present' }))
  fireEvent.click(screen.getByRole('button', { name: 'Save Attendance' }))
  await screen.findByText('Attendance saved locally. It will synchronize when you reconnect.')
  const queue = await queuedOperations(scope)
  assert.equal(queue.length, 1)
  assert.equal(queue[0].payload.entries.length, 2)
  assert.equal(queue[0].path, '/school/attendance/bulk/')
  await clearOfflineScope(scope)
})

test('uncached offline attendance explains why no class can be opened', async () => {
  render(React.createElement(OfflineContext.Provider, { value: { scope: `uncached:${crypto.randomUUID()}`, isReachable: false } }, React.createElement(AttendancePage)))
  await screen.findByText('No attendance class list is cached. Connect to load your school classes.')
  assert.equal(Boolean(screen.queryByRole('button', { name: 'Save Attendance' })), false)
})


test('all attendance selections survive a sync refresh before explicit Save', async () => {
  const scope = `draft:${crypto.randomUUID()}`
  saved = []
  const view = (revision) => React.createElement(OfflineContext.Provider, { value: { scope, isReachable: true, syncRevision: revision } }, React.createElement(AttendancePage))
  const rendered = render(view(0))
  fireEvent.click(await screen.findByRole('button', { name: 'Grade 3' }))
  await screen.findByRole('button', { name: 'Mark All Present' })
  const group = () => within(screen.getByRole('group', { name: 'Attendance for Tariro Moyo' }))
  for (const label of ['Absent', 'Late', 'Excused', 'Present', 'Absent']) {
    fireEvent.click(group().getByRole('button', { name: label }))
    assert.equal(group().getByRole('button', { name: label }).getAttribute('aria-pressed'), 'true')
  }
  const before = rosterRequests
  rendered.rerender(view(1))
  await waitFor(() => assert.ok(rosterRequests > before))
  await screen.findByRole('button', { name: 'Mark All Present' })
  assert.equal(group().getByRole('button', { name: 'Absent' }).getAttribute('aria-pressed'), 'true')
  assert.equal(saved.length, 0)
  fireEvent.click(screen.getByRole('button', { name: 'Save Attendance' }))
  await waitFor(() => assert.equal(saved.length, 1))
  assert.equal(saved[0].entries[0].status, 'absent')
  await clearOfflineScope(scope)
})

test('offline selected exceptions restore after remount and history opens', async () => {
  const scope = `restore:${crypto.randomUUID()}`
  await cacheAttendanceLookups(scope, { classes, years, terms })
  await cacheAttendanceRoster(scope, roster)
  const view = () => React.createElement(OfflineContext.Provider, { value: { scope, isReachable: false } }, React.createElement(AttendancePage))
  const first = render(view())
  fireEvent.click(await screen.findByRole('button', { name: 'Grade 3' }))
  await screen.findByRole('button', { name: 'Mark All Present' })
  fireEvent.click(within(screen.getByRole('group', { name: 'Attendance for Tariro Moyo' })).getByRole('button', { name: 'Excused' }))
  fireEvent.click(screen.getByRole('button', { name: 'Save Attendance' }))
  await screen.findByText('Attendance saved locally. It will synchronize when you reconnect.')
  assert.equal((await queuedOperations(scope))[0].payload.entries[0].status, 'excused')
  first.unmount()
  render(view())
  fireEvent.click(await screen.findByRole('button', { name: 'Grade 3' }))
  await screen.findByRole('button', { name: 'Mark All Present' })
  assert.equal(within(screen.getByRole('group', { name: 'Attendance for Tariro Moyo' })).getByRole('button', { name: 'Excused' }).getAttribute('aria-pressed'), 'true')
  fireEvent.click(screen.getByRole('button', { name: 'Attendance History' }))
  await screen.findByRole('heading', { name: 'Attendance History' })
  await clearOfflineScope(scope)
})

test('timetable explicit scopes and historical year terms', () => {
  function Editor() {
    const [form, setForm] = React.useState({ name: 'Whole', scope: 'SINGLE', academic_year: '2', term: '', classes: [], entries: [] })
    return React.createElement(TimetableEditor, { form, setForm, lookups: { classes, years: [...years, { id: 2, name: '2025' }], terms: [...terms, { id: 2, academic_year: 2, name: 'Historical Term' }], activities: [], subjects: [] }, onSave: (e) => e.preventDefault() })
  }
  render(React.createElement(Editor))
  assert.ok(screen.getByRole('option', { name: '2025' }))
  assert.ok(screen.getByRole('option', { name: 'Historical Term' }))
  assert.equal(Boolean(screen.queryByRole('option', { name: 'Term 1' })), false)
  assert.ok(screen.getByLabelText('Class'))
  fireEvent.change(screen.getByLabelText('Applies To'), { target: { value: 'MULTIPLE' } })
  assert.ok(screen.getByLabelText('Grade 3'))
  fireEvent.change(screen.getByLabelText('Applies To'), { target: { value: 'WHOLE_SCHOOL' } })
  assert.equal(Boolean(screen.queryByLabelText('Grade 3')), false)
  assert.ok(screen.getByText(/including classes added later/))
})


test('year and term dropdowns survive a timetable list request failure', async () => {
  academicMock = async (resource) => { if (resource === 'timetable-plans') throw new Error('List failed'); return ({ classes, 'academic-years': years, terms, subjects: [], 'subjects/library': { groups: [], activities: ['Break'] } })[resource] }
  render(React.createElement(TimetablesPage))
  await screen.findByRole('option', { name: 'Current year' })
  fireEvent.change(screen.getByLabelText('Academic Year'), { target: { value: '1' } })
  assert.ok(screen.getByRole('option', { name: 'Term 1' }))
  assert.equal(Boolean(screen.queryByRole('link', { name: /Curriculum Setup/ })), false)
})

function fillFee(method = 'MONTHLY') {
  fireEvent.change(screen.getByLabelText('Billing Method'), { target: { value: method } })
  fireEvent.change(screen.getByLabelText('Fee Name'), { target: { value: 'Tuition' } })
  const input = screen.getByRole('spinbutton')
  assert.equal(input.step, '1')
  fireEvent.change(input, { target: { value: '75' } })
  input.stepUp()
  assert.equal(input.value, '76')
  fireEvent.change(input, { target: { value: '75.50' } })
  fireEvent.change(screen.getByLabelText('Academic Year'), { target: { value: '1' } })
  fireEvent.change(screen.getByLabelText('Term'), { target: { value: '1' } })
}

test('Fees/Charges forms submit each billing method with cents and conditional scope', async () => {
  for (const method of ['MONTHLY', 'TERMLY', 'ONE_OFF']) {
    let payload
    saveFeeMock = async (resource, data) => { payload = data; return { id: 7, is_active: false } }
    const view = render(React.createElement(FeeManagementPage))
    await screen.findByRole('option', { name: 'Current year' })
    assert.equal(Boolean(screen.queryByRole('button', { name: 'Assignments / Scope' })), false)
    fillFee(method)
    fireEvent.change(screen.getByLabelText('Scope'), { target: { value: 'class' } })
    fireEvent.change(screen.getByLabelText('Class / Grade'), { target: { value: '1' } })
    fireEvent.change(screen.getByLabelText('Scope'), { target: { value: 'school' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save and preview' }))
    await waitFor(() => assert.ok(payload))
    assert.equal(payload.billing_method, method)
    assert.equal(payload.amount, '75.50')
    assert.equal(payload.school_class, null)
    assert.equal(payload.student, null)
    for (const hidden of ['currency', 'start_month', 'end_month']) assert.equal(hidden in payload, false)
    await screen.findByText('Fee structure saved. No charges have been created.')
    fireEvent.click(screen.getByRole('button', { name: 'Charges', exact: true }))
    assert.ok(screen.getByLabelText('Student search'))
    view.unmount()
  }
})

test('fee field errors retain their field names and generation requires confirmation', async () => {
  saveFeeMock = async () => { throw { data: { academic_year: ['This field is required.'], term: ['This field is required.'] } } }
  const view = render(React.createElement(FeeManagementPage))
  await screen.findByRole('option', { name: 'Current year' })
  fillFee()
  fireEvent.click(screen.getByRole('button', { name: 'Save and preview' }))
  await waitFor(() => assert.equal(screen.getAllByText('This field is required.').length, 2))
  const messages = screen.getAllByText('This field is required.')
  assert.ok(messages[0].closest('label').textContent.includes('Academic Year'))
  assert.ok(messages[1].closest('label').textContent.includes('Term'))
  assert.equal(Boolean(screen.queryByRole('alert')), false)
  view.unmount()
  financeData['recurring-fees'] = [{ id: 7, name: 'Tuition', billing_method: 'MONTHLY', amount: '75.50', currency: 'USD', academic_year: 1, term: 1, is_active: true, can_delete: true }]
  const calls = []
  apiMock = async (path, options) => { calls.push([path, options]); return options ? { assignments_created: 2 } : { name: 'Tuition', periods: [], missing_enrollments: [], total_charges: 2, preview_token: 'confirmed-token' } }
  render(React.createElement(FeeManagementPage))
  fireEvent.click(await screen.findByRole('button', { name: 'Preview charges' }))
  await screen.findByRole('button', { name: 'Confirm and generate 2 charges' })
  assert.equal(calls.length, 1)
  fireEvent.click(screen.getByRole('button', { name: 'Confirm and generate 2 charges' }))
  await screen.findByText('2 charges created.')
  assert.deepEqual(JSON.parse(calls[1][1].body), { confirm: true, preview_token: 'confirmed-token' })
})

test('parent statement displays letterhead, filters and a read-only printable report', async () => {
  const calls = []
  apiMock = async (path) => { calls.push(path); return { school: { name: 'School A', address: '1 School Road' }, student: { name: 'Tariro', admission_number: '001', class_name: 'Grade 3' }, currency: 'USD', generated_at: '2026-10-06T10:00:00Z', years, terms, transactions: [{ date: '2026-01-14', reference: 'FEE-1', description: 'Tuition', debit: '100', credit: '0', balance: '100' }], summary: { opening_balance: '0', charges: '100', payments: '0', adjustments_reversals: '0', closing_balance: '100' } } }
  let printed = false
  window.print = () => { printed = true }
  render(React.createElement(AccountStatementPage, { parent: true }))
  await screen.findByText('STATEMENT OF ACCOUNT')
  assert.ok(screen.getByText('1 School Road'))
  assert.ok(screen.getByText('FEE-1'))
  assert.equal(Boolean(screen.queryByRole('img')), false)
  assert.equal(Boolean(screen.queryByRole('button', { name: /delete|edit|save payment/i })), false)
  fireEvent.change(screen.getByLabelText('Academic Year'), { target: { value: '1' } })
  await screen.findByText('STATEMENT OF ACCOUNT')
  assert.match(calls.at(-1), /parent\/students\/1\/statement\/\?academic_year=1/)
  fireEvent.click(screen.getByRole('button', { name: 'Print / Save PDF' }))
  assert.equal(printed, true)
  const css = await readFile(new URL('./App.css', import.meta.url), 'utf8')
  assert.match(css, /a, :where\(a:visited\)\s*\{ color: #1755a0/)
  assert.match(css, /a:focus-visible/)
  assert.match(css, /@media print/)
  assert.match(css, /statement-controls.*display: none/)
  assert.match(css, /button\[aria-pressed="true"\]/)
})


test('built-in and custom subjects are selected directly with no setup page', async () => {
  academicMock = async () => ({ groups: [{ name: 'Primary', subjects: [{ key: 'ZW-english', name: 'English Language' }] }] })
  const requests = []
  subjectSaveMock = async (resource, payload) => { requests.push([resource, payload]); return resource === 'subjects/activate' ? [{ id: 33, name: 'English Language', is_active: true }] : { id: 34, name: payload.name, is_active: true } }
  let value
  function Picker() { const [selected, setSelected] = React.useState(''); value = selected; return React.createElement(SubjectPicker, { value: selected, onChange: setSelected }) }
  render(React.createElement(Picker))
  fireEvent.focus(screen.getByLabelText('Subject'))
  fireEvent.click(await screen.findByRole('option', { name: /English Language/ }))
  await waitFor(() => assert.equal(value, 33))
  assert.deepEqual(requests[0], ['subjects/activate', { keys: ['ZW-english'] }])
  fireEvent.focus(screen.getByLabelText('Subject'))
  fireEvent.click(screen.getByRole('option', { name: 'Other / Custom Subject' }))
  fireEvent.change(screen.getByLabelText('Custom subject name'), { target: { value: 'Robotics' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add custom subject' }))
  await waitFor(() => assert.equal(value, 34))
  assert.equal(requests[1][0], 'subjects')
})


test('subject autocomplete filters partial names and supports mouse, arrows, Enter and Escape', async () => {
  const names = ['English Language', 'English for Communication', 'Literature in English', 'Mathematics', 'Functional Mathematics', 'Additional Mathematics', 'Pure Mathematics']
  academicMock = async () => ({ groups: [{ name: 'Zimbabwe', subjects: names.map((name, index) => ({ key: `ZW-${index}`, name })) }] })
  subjectSaveMock = async (resource, payload) => [{ id: 50, name: names[Number(payload.keys[0].slice(3))], is_active: true }]
  let value
  function Picker() { const [selected, setSelected] = React.useState(''); value = selected; return React.createElement(SubjectPicker, { value: selected, onChange: setSelected, subjects: [{ id: 99, name: 'Robotics', is_active: true }] }) }
  render(React.createElement(Picker))
  const input = screen.getByRole('combobox', { name: 'Subject' })
  fireEvent.change(input, { target: { value: 'eNg' } })
  await screen.findByRole('option', { name: /English Language/ })
  assert.equal(screen.getAllByRole('option').length, 4)
  assert.equal(Boolean(screen.queryByRole('option', { name: /Assembly|Break|Lunch|Sports/ })), false)
  fireEvent.change(input, { target: { value: 'Math' } })
  assert.equal(screen.getAllByRole('option').length, 5)
  fireEvent.keyDown(input, { key: 'ArrowDown' })
  fireEvent.keyDown(input, { key: 'ArrowUp' })
  fireEvent.keyDown(input, { key: 'Enter' })
  await waitFor(() => assert.equal(value, 50))
  assert.equal(input.value, 'Mathematics')
  assert.equal(input.getAttribute('aria-expanded'), 'false')
  fireEvent.change(input, { target: { value: 'robot' } })
  assert.equal(value, '')
  fireEvent.keyDown(input, { key: 'Escape' })
  assert.equal(Boolean(screen.queryByRole('listbox')), false)
  fireEvent.keyDown(input, { key: 'ArrowDown' })
  fireEvent.keyDown(input, { key: 'Enter' })
  assert.equal(value, 99)
  assert.equal(input.value, 'Robotics')
})

test('attendance selected buttons are blue, other statuses grey, and Mark All is local', async () => {
  const style = document.createElement('style')
  const css = await readFile(new URL('./App.css', import.meta.url), 'utf8')
  style.textContent = css.split('\n').filter((line) => line.startsWith('.attendance-status-buttons') && !line.includes(':hover')).join('\n')
  document.head.append(style)
  const scope = `visual:${crypto.randomUUID()}`
  academicMock = async (resource) => ({ classes, 'academic-years': years, terms })[resource]
  saved = []
  render(React.createElement(OfflineContext.Provider, { value: { scope, isReachable: true } }, React.createElement(AttendancePage)))
  fireEvent.click(await screen.findByRole('button', { name: 'Grade 3' }))
  await screen.findByRole('button', { name: 'Mark All Present' })
  const group = within(screen.getByRole('group', { name: 'Attendance for Tariro Moyo' }))
  for (const name of ['Absent', 'Late', 'Excused', 'Present']) {
    fireEvent.click(group.getByRole('button', { name }))
    assert.equal(group.getAllByRole('button', { pressed: true }).length, 1)
    for (const button of group.getAllByRole('button')) {
      assert.equal(window.getComputedStyle(button).backgroundColor, button.textContent === name ? 'rgb(23, 85, 160)' : 'rgb(241, 243, 245)')
    }
  }
  fireEvent.click(group.getByRole('button', { name: 'Absent' }))
  fireEvent.click(screen.getByRole('button', { name: 'Mark All Present' }))
  assert.equal(saved.length, 0)
  for (const row of screen.getAllByRole('group')) assert.equal(within(row).getByRole('button', { pressed: true }).textContent, 'Present')
  style.remove()
  await clearOfflineScope(scope)
})
