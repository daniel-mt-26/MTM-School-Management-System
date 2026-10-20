import assert from 'node:assert/strict'
import 'fake-indexeddb/auto'
import { test, after, afterEach } from 'node:test'
import { readFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import { Buffer } from 'node:buffer'
import React from 'react'
import { JSDOM } from 'jsdom'
import { transformWithOxc } from 'vite'
import { AuthContext } from './auth/context.js'
import { enqueueOperation, queuedOperations, clearOfflineScope } from './offline/db.js'

const dom = new JSDOM('<html><body></body></html>', { url: 'http://localhost/reset-password#token=test-token' })
globalThis.window = dom.window; globalThis.document = dom.window.document
globalThis.HTMLElement = dom.window.HTMLElement; globalThis.IS_REACT_ACT_ENVIRONMENT = true
globalThis.Element = dom.window.Element
globalThis.localStorage = dom.window.localStorage
globalThis.Event = dom.window.Event
const { render, screen, fireEvent, cleanup, waitFor, act } = await import('@testing-library/react')
const require = createRequire(import.meta.url)
let section = '', requests = [], downloads = []
const lookups = { school_name: 'School A', profile: { email: 'teacher@test.example' }, classes: [{ id: 1, name: 'Assigned Grade' }], subjects: [], years: [{ id: 1, name: '2026' }], terms: [{ id: 1, name: 'Term 1', academic_year: 1 }], enrollments: [] }
let handler = async path => path.includes('lookups') ? lookups : []
const mocks = {
  'react-router-dom': { useParams: () => ({ section }), Link: ({ to, children, ...props }) => React.createElement('a', { href: to, ...props }, children) },
  '../auth/context': { AuthContext },
  '../api/client': { apiClient: async (...args) => { requests.push(args); return handler(...args) }, apiDownload: async (...args) => { downloads.push(args) }, setAuthenticationFailureHandler() {}, setApplicationRole() {} },
  '../api/auth': { login: async () => ({ access: 'test-access', refresh: 'test-refresh' }), tokenStorage: { getAccess: () => null, setTokens() {}, clear() {} } },
  './AttendancePage': { default: () => React.createElement('div', null, 'Attendance tool') },
  './HomeworkPage': { default: () => React.createElement('div', null, 'Homework tool') },
}
globalThis.teacherUiMocks = mocks
const dataUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const cache = new Map()
async function compile(url) {
  if (cache.has(url.href)) return cache.get(url.href)
  let code = (await transformWithOxc(await readFile(url, 'utf8'), url.pathname, { jsx: { runtime: 'automatic' } })).code
  for (const match of [...code.matchAll(/from (["'])([^"']+)\1/g)]) {
    const specifier = match[2]
    let resolved
    if (mocks[specifier]) resolved = dataUrl(Object.keys(mocks[specifier]).map(key => key === 'default' ? `export default globalThis.teacherUiMocks[${JSON.stringify(specifier)}].default;` : `export const ${key}=globalThis.teacherUiMocks[${JSON.stringify(specifier)}][${JSON.stringify(key)}];`).join('\n'))
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
const TeacherPortal = await load('./pages/TeacherPortal.jsx')
const SortableTable = await load('./components/SortableTable.jsx')
const Register = await load('./components/AttendanceRegister.jsx')
const Recovery = await load('./pages/PasswordRecoveryPage.jsx')
const { AuthProvider } = await import(await compile(new URL('./auth/AuthContext.jsx', import.meta.url)))
afterEach(() => { cleanup(); section = ''; requests = []; downloads = []; handler = async path => path.includes('lookups') ? lookups : [] })
after(() => dom.window.close())

test('teacher portal renders assigned classes and correct restricted navigation', async () => {
  section = 'classes'
  render(React.createElement(AuthContext.Provider, { value: { user: { id: 1, role: 'teacher' }, logout() {} } }, React.createElement(TeacherPortal)))
  await screen.findByRole('heading', { name: 'Assigned Grade' })
  assert.equal(screen.queryByRole('link', { name: /Finance|School Settings|Platform/i }), null)
  assert.equal(screen.getByRole('link', { name: 'My Classes' }).getAttribute('href'), '/teacher/classes')
})
test('table heading changes ascending and descending order with indicators', () => {
  render(React.createElement(SortableTable, {}, React.createElement('thead', {}, React.createElement('tr', {}, React.createElement('th', {}, 'Amount'))), React.createElement('tbody', {}, [100, 11, 2].map(n => React.createElement('tr', { key: n }, React.createElement('td', {}, n))))))
  fireEvent.click(screen.getByRole('button', { name: 'Amount' }))
  assert.deepEqual(screen.getAllByRole('cell').map(c => c.textContent), ['2', '11', '100'])
  assert.equal(screen.getByRole('columnheader').getAttribute('aria-sort'), 'ascending')
  fireEvent.click(screen.getByRole('button', { name: 'Amount ▲' }))
  assert.deepEqual(screen.getAllByRole('cell').map(c => c.textContent), ['100', '11', '2'])
  assert.equal(screen.getByRole('columnheader').getAttribute('aria-sort'), 'descending')
})
test('monthly register filters load codes and exports use protected endpoint', async () => {
  handler = async () => ({ school: 'School A', school_class: 'Assigned Grade', academic_year: '2026', term: 'Term 1', month: 'February 2026', generated_at: '2026-02-28T12:00:00Z', teachers: [['Jane', 'Smith']], days: [1, 2], rows: [{ id: 1, student_name: 'Amy', admission_number: '002', days: ['P', 'A'], present: 1, absent: 1, late: 0, excused: 0, percentage: 50 }] })
  render(React.createElement(Register, { lookups }))
  for (const [label, value] of [['Academic Year', '1'], ['Term', '1'], ['Class', '1'], ['Month', '2']]) fireEvent.change(screen.getByLabelText(label), { target: { value } })
  await screen.findByText('Amy')
  assert.ok(screen.getByText('50%'))
  fireEvent.click(screen.getByRole('button', { name: 'Export Excel' }))
  assert.match(downloads[0][0], /school\/attendance\/register\/.*export=xlsx/)
  let printed = false; window.print = () => { printed = true }
  fireEvent.click(screen.getByRole('button', { name: 'Print Register' })); assert.equal(printed, true)
})
test('forgot password sends identifier and renders neutral confirmation', async () => {
  handler = async () => ({ detail: 'If an account matching those details exists, password reset instructions have been sent.' })
  render(React.createElement(Recovery))
  fireEvent.change(screen.getByLabelText('Username or email'), { target: { value: 'teacher' } })
  fireEvent.click(screen.getByRole('button', { name: 'Send reset instructions' }))
  await screen.findByRole('status')
  assert.equal(requests[0][0], '/auth/forgot-password/')
  assert.deepEqual(JSON.parse(requests[0][1].body), { identifier: 'teacher' })
})
test('reset removes token from browser URL and submits it once to the reset endpoint', async () => {
  window.history.replaceState(null, '', '/reset-password#token=test-token')
  handler = async () => ({ detail: 'Password reset successfully.' })
  render(React.createElement(Recovery, { reset: true }))
  assert.equal(window.location.hash, '')
  fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'new-strong-password-975!' } })
  fireEvent.click(screen.getByRole('button', { name: 'Reset password' }))
  await waitFor(() => assert.equal(requests[0][0], '/auth/reset-password/'))
  assert.equal(JSON.parse(requests[0][1].body).token, 'test-token')
})

test('inactivity warning, real activity, Stay Signed In and expiry preserve isolated offline work', async () => {
  const clock = Date.now, schedule = globalThis.setInterval, cancel = globalThis.clearInterval
  let now = 1000, tick
  Date.now = () => now
  globalThis.setInterval = (callback, delay) => { if (delay === 1000) { tick = callback; return -1 } return schedule(callback, delay) }
  globalThis.clearInterval = id => { if (id !== -1) cancel(id) }
  const scope = 'user:99:teacher'
  await clearOfflineScope(scope)
  await enqueueOperation(scope, { module: 'homework', entity: 'homework', action: 'create', method: 'POST', path: '/teacher/homework/', payload: { title: 'Queued worksheet' } })
  handler = async () => ({ id: 99, role: 'teacher', username: 'teacher', must_change_password: false })
  function Probe() {
    const auth = React.useContext(AuthContext)
    return React.createElement('div', {}, React.createElement('p', {}, auth.user ? 'Protected teacher screen' : 'Login required'), React.createElement('button', { onClick: () => auth.signIn('teacher', 'test') }, 'Sign in'))
  }
  try {
    render(React.createElement(AuthProvider, {}, React.createElement(Probe)))
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await screen.findByText('Protected teacher screen')
    now += 28 * 60 * 1000
    act(() => tick())
    assert.ok(screen.getByRole('alertdialog'))
    fireEvent.click(screen.getByRole('button', { name: 'Stay Signed In' }))
    await waitFor(() => assert.equal(screen.queryByRole('alertdialog'), null))
    now += 27 * 60 * 1000
    fireEvent.pointerDown(window)
    now += 27 * 60 * 1000
    act(() => tick())
    assert.equal(screen.queryByRole('alertdialog'), null)
    now += 3 * 60 * 1000
    act(() => tick())
    assert.ok(screen.getByText('Login required'))
    assert.equal(screen.queryByText('Protected teacher screen'), null)
    assert.equal((await queuedOperations(scope)).length, 1)
    assert.equal((await queuedOperations('user:100:teacher')).length, 0)
  } finally {
    cleanup(); Date.now = clock; globalThis.setInterval = schedule; globalThis.clearInterval = cancel
    await clearOfflineScope(scope)
  }
})
