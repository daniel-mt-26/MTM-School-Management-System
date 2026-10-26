import 'fake-indexeddb/auto'
import assert from 'node:assert/strict'
import { after, afterEach, test } from 'node:test'
import { readFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import { Buffer } from 'node:buffer'
import React from 'react'
import { JSDOM } from 'jsdom'
import { transformWithOxc } from 'vite'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { AuthContext } from './context.js'
import * as authApi from '../api/auth.js'
import * as client from '../api/client.js'
import { beginSession, INACTIVITY_MESSAGE, INACTIVITY_MS, publishLogout } from './inactivity.js'
import { routeForRole, roleRoutes } from './roleRoutes.js'
import { clearOfflineScope, enqueueOperation, queuedOperations } from '../offline/db.js'

const dom = new JSDOM('<html><body></body></html>', { url: 'http://localhost' })
Object.assign(globalThis, { window: dom.window, document: dom.window.document, HTMLElement: dom.window.HTMLElement,
  sessionStorage: dom.window.sessionStorage, localStorage: dom.window.localStorage, IS_REACT_ACT_ENVIRONMENT: true })
const { render, screen, fireEvent, cleanup, waitFor, act } = await import('@testing-library/react')
const require = createRequire(import.meta.url), cache = new Map()
const empty = async () => []
const mocks = {
  '../auth/context': { AuthContext }, './context': { AuthContext },
  '../api/auth': authApi, '../api/client': client,
  '../api/school': { getSchoolProfile: async () => ({ name: 'Test School' }), searchSchool: empty },
  '../api/platform': { platformDashboard: async () => ({ recently_created_schools: [] }) },
  '../api/finance': { downloadReceiptPdf: empty, getParentStudentFinance: empty },
  '../api/communication': { getParentCommunicationPreference: async () => null, getParentNotifications: empty, markNotificationRead: empty, updateParentCommunicationPreference: empty },
  './AttendancePage': { default: () => null }, './HomeworkPage': { default: () => null },
}
globalThis.logoutUiMocks = mocks
const dataUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
async function compile(url) {
  if (cache.has(url.href)) return cache.get(url.href)
  let code = (await transformWithOxc(await readFile(url, 'utf8'), url.pathname, { jsx: { runtime: 'automatic' } })).code
  for (const match of [...code.matchAll(/from (["'])([^"']+)\1/g)]) {
    const specifier = match[2]
    let resolved
    if (mocks[specifier]) resolved = dataUrl(Object.keys(mocks[specifier]).map(key => key === 'default'
      ? `export default globalThis.logoutUiMocks[${JSON.stringify(specifier)}].default;`
      : `export const ${key} = globalThis.logoutUiMocks[${JSON.stringify(specifier)}][${JSON.stringify(key)}];`).join('\n'))
    else if (specifier.startsWith('.')) {
      const relative = new URL(/\.(js|jsx)$/.test(specifier) ? specifier : specifier + (existsSync(new URL(specifier + '.jsx', url)) ? '.jsx' : '.js'), url)
      resolved = relative.pathname.endsWith('.jsx') ? await compile(relative) : relative.href
    } else resolved = pathToFileURL(require.resolve(specifier)).href
    code = code.replace(match[0], `from ${JSON.stringify(resolved)}`)
  }
  const result = dataUrl(code); cache.set(url.href, result); return result
}
const load = async path => (await import(await compile(new URL(path, import.meta.url)))).default
const { AuthProvider } = await import(await compile(new URL('./AuthContext.jsx', import.meta.url)))
const ProtectedRoute = await load('./ProtectedRoute.jsx')
const LoginPage = await load('../pages/LoginPage.jsx')
const dashboards = {
  platform_admin: await load('../pages/PlatformDashboard.jsx'), school_admin: await load('../pages/SchoolDashboard.jsx'),
  teacher: await load('../pages/TeacherPortal.jsx'), parent: await load('../pages/ParentDashboard.jsx'),
}
const original = { now: Date.now, schedule: globalThis.setTimeout, cancel: globalThis.clearTimeout, fetch: globalThis.fetch }
let now, timers, sequence, profile, requests, auth, navigate
function setup(role, restore = true) {
  now = 1000000; timers = new Map(); sequence = 0; requests = []
  profile = { id: 99, role, username: role, must_change_password: false }
  Date.now = () => now
  globalThis.setTimeout = (fn, delay, ...args) => {
    // Keep Testing Library's own polling on the real clock.
    if (fn.name === 'check') { const id = --sequence; timers.set(id, { fn, due: now + delay }); return id }
    return original.schedule(fn, delay, ...args)
  }
  globalThis.clearTimeout = id => { if (!timers.delete(id)) original.cancel(id) }
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options })
    let data = []
    if (url.endsWith('/auth/me/')) data = profile
    if (url.endsWith('/auth/token/')) data = { access: 'access', refresh: 'refresh' }
    if (url.endsWith('/teacher/lookups/')) data = { school_name: 'Test School', classes: [], subjects: [], years: [], terms: [], enrollments: [] }
    if (url.endsWith('/teacher/dashboard/')) data = {}
    return new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }
  if (restore) { authApi.tokenStorage.setTokens({ access: 'access', refresh: 'refresh' }); beginSession(profile) }
}
function Probe() {
  auth = React.useContext(AuthContext)
  navigate = useNavigate()
  return React.createElement('output', { 'data-testid': 'location' }, useLocation().pathname)
}
function mount(path = routeForRole(profile.role)) {
  return render(React.createElement(React.StrictMode, {}, React.createElement(MemoryRouter, { initialEntries: [path] },
    React.createElement(AuthProvider, {}, React.createElement(Probe), React.createElement(Routes, {},
      React.createElement(Route, { path: '/login', element: React.createElement(LoginPage) }),
      ...Object.entries(dashboards).map(([role, Dashboard]) => React.createElement(Route, { key: role, element: React.createElement(ProtectedRoute, { allowedRole: role }) },
        React.createElement(Route, { path: roleRoutes[role], element: React.createElement(Dashboard) }))),
    )))))
}
function advance(ms) {
  const end = now + ms
  act(() => {
    while (true) {
      const entry = [...timers].filter(([, timer]) => timer.due <= end).sort((a, b) => a[1].due - b[1].due)[0]
      if (!entry) break
      const [id, timer] = entry; timers.delete(id); now = timer.due; timer.fn()
    }
    now = end
  })
}
function assertLoggedOut(message) {
  assert.equal(authApi.tokenStorage.getAccess(), null)
  assert.equal(authApi.tokenStorage.getRefresh(), null)
  assert.equal(sessionStorage.getItem('mtm_session_account'), null)
  assert.equal(screen.getByTestId('location').textContent, '/login')
  assert.ok(screen.getByRole('heading', { name: 'Sign in' }))
  if (message) assert.equal(screen.getByRole('alert').textContent, message)
  else assert.equal(screen.queryByRole('alert'), null)
  assert.equal(timers.size, 0)
}
async function ready() {
  await screen.findByRole('navigation', { name: 'Account menu' })
  await waitFor(() => assert.equal(timers.size, 1))
}
afterEach(() => {
  cleanup(); sessionStorage.clear(); localStorage.clear()
  Date.now = original.now; globalThis.setTimeout = original.schedule; globalThis.clearTimeout = original.cancel; globalThis.fetch = original.fetch
})
after(() => dom.window.close())

for (const role of Object.keys(dashboards)) {
  test(`${role}: visible account menu logs out, clears both JWTs and protects routes`, async () => {
    setup(role); mount()
    await ready()
    assert.equal(requests.filter(request => request.url.endsWith('/auth/me/')).length, 1)
    assert.equal(timers.size, 1)
    fireEvent.click(screen.getByRole('button', { name: 'Logout', exact: true }))
    assertLoggedOut()
    act(() => navigate(routeForRole(role)))
    assertLoggedOut()
    assert.equal(requests.some(request => request.url.includes('/logout')), false)
  })

  test(`${role}: inactivity redirects at 600 seconds with the exact message`, async () => {
    setup(role); mount()
    await ready()
    advance(INACTIVITY_MS - 1)
    assert.equal(auth.user.role, role)
    advance(1)
    assertLoggedOut(INACTIVITY_MESSAGE)
    const signal = localStorage.getItem(`mtm:logout:99:${role}`)
    act(() => { window.dispatchEvent(new window.Event('focus')); auth.logout() })
    assert.equal(localStorage.getItem(`mtm:logout:99:${role}`), signal)
    assertLoggedOut(INACTIVITY_MESSAGE)
  })
}

test('background profile requests do not reset the inactivity deadline', async () => {
  setup('teacher'); mount(); await ready()
  advance(590000)
  await act(async () => { await auth.refreshCurrentUser(); await client.apiClient('/teacher/lookups/') })
  advance(10000); assertLoggedOut(INACTIVITY_MESSAGE)
})

test('returning to a suspended tab immediately logs out before interaction', async () => {
  setup('parent'); mount(); await ready()
  now += INACTIVITY_MS + 1000
  act(() => document.dispatchEvent(new window.Event('visibilitychange')))
  assertLoggedOut(INACTIVITY_MESSAGE)
})

test('reload after inactivity never mounts the protected dashboard', async () => {
  setup('school_admin'); now += INACTIVITY_MS
  mount()
  await screen.findByRole('heading', { name: 'Sign in' })
  assertLoggedOut(INACTIVITY_MESSAGE)
  assert.equal(screen.queryByRole('navigation', { name: 'Account menu' }), null)
  assert.equal(requests.length, 0)
})

for (const message of ['', INACTIVITY_MESSAGE]) {
  test(`cross-tab logout clears this tab's tokens and preserves the logout reason (${message ? 'automatic' : 'manual'})`, async () => {
    setup('teacher'); mount(); await ready()
    act(() => {
      publishLogout(profile, message, true)
      window.dispatchEvent(new window.StorageEvent('storage', { key: 'mtm:logout:99:teacher', newValue: localStorage.getItem('mtm:logout:99:teacher') }))
    })
    assertLoggedOut(message)
  })
}

test('fresh login after expiration clears the warning and starts a new deadline', async () => {
  setup('parent'); mount(); await ready()
  advance(INACTIVITY_MS); assertLoggedOut(INACTIVITY_MESSAGE)
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'parent' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'test-only' } })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  await ready()
  assert.equal(auth.sessionMessage, '')
  advance(INACTIVITY_MS - 1); assert.ok(auth.user)
  advance(1); assertLoggedOut(INACTIVITY_MESSAGE)
})

test('automatic logout retains queued work under its original account scope', async () => {
  const scope = 'user:99:teacher'
  await clearOfflineScope(scope)
  await enqueueOperation(scope, { module: 'homework', entity: 'homework', action: 'create', method: 'POST', path: '/teacher/homework/', payload: { title: 'Queued worksheet' } })
  setup('teacher'); mount(); await ready()
  advance(INACTIVITY_MS); assertLoggedOut(INACTIVITY_MESSAGE)
  assert.equal((await queuedOperations(scope)).length, 1)
  assert.equal((await queuedOperations('user:100:teacher')).length, 0)
  await clearOfflineScope(scope)
})

test('unmount removes the timer and logout listeners', async () => {
  setup('teacher'); const view = mount(); await ready()
  view.unmount(); assert.equal(timers.size, 0)
  const access = authApi.tokenStorage.getAccess()
  now += INACTIVITY_MS
  window.dispatchEvent(new window.Event('focus'))
  assert.equal(authApi.tokenStorage.getAccess(), access)
})

test('a profile refresh completing after logout cannot restore the protected session', async () => {
  setup('teacher'); mount(); await ready()
  let finish
  const initialFetch = globalThis.fetch
  globalThis.fetch = (url, options) => url.endsWith('/auth/me/')
    ? new Promise(resolve => { finish = resolve }) : initialFetch(url, options)
  const pending = auth.refreshCurrentUser()
  const rejected = assert.rejects(pending, /Session changed/)
  await act(async () => { await Promise.resolve() })
  fireEvent.click(screen.getByRole('button', { name: 'Logout', exact: true }))
  assertLoggedOut()
  await act(async () => {
    finish(new Response(JSON.stringify(profile), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    await rejected
  })
  assertLoggedOut()
})
