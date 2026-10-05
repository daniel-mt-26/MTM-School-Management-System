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
  'react-router-dom': { Link: ({ to, children, ...props }) => React.createElement('a', { href: to, ...props }, children) },
  '../offline/context': { OfflineContext },
  '../api/academics': { getAcademicRecords: async (resource) => ({ classes, 'academic-years': years, terms })[resource] },
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
      const relative = new URL(/\.(js|jsx)$/.test(specifier) ? specifier : specifier + (specifier.includes('components/') ? '.jsx' : '.js'), url)
      resolved = relative.pathname.endsWith('.jsx') ? await compile(relative) : relative.href
    } else resolved = pathToFileURL(require.resolve(specifier)).href
    code = code.replace(match[0], `from ${JSON.stringify(resolved)}`)
  }
  const result = dataUrl(code)
  moduleCache.set(url.href, result)
  return result
}
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

test('dashboard retains Attendance and Timetables without duplicate subject cards', () => {
  render(React.createElement(AcademicsPage))
  assert.ok(screen.getByRole('heading', { name: 'Attendance' }))
  assert.ok(screen.getByRole('heading', { name: 'Timetables' }))
  assert.equal(screen.queryByRole('heading', { name: 'Subjects' }), null)
  assert.equal(screen.queryByRole('heading', { name: 'Class Subjects' }), null)
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
  assert.equal(screen.queryByRole('option', { name: 'Inactive subject' }), null)
  assert.ok(screen.getByRole('option', { name: 'Mathematics' }))
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
  assert.equal(screen.queryByRole('button', { name: 'Save Attendance' }), null)
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
  assert.equal(screen.queryByRole('button', { name: 'Save Attendance' }), null)
})
