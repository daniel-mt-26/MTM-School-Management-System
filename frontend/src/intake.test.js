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
import { AuthContext } from './auth/context.js'
import { tokenStorage } from './api/auth.js'
import { setAuthenticationFailureHandler } from './api/client.js'
import * as actual from './api/intake.js'
import { queuedOperations, cachedValue } from './offline/db.js'

const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'http://localhost',
  pretendToBeVisual: true,
})
globalThis.window = dom.window
globalThis.document = dom.window.document
globalThis.HTMLElement = dom.window.HTMLElement
globalThis.sessionStorage = dom.window.sessionStorage
globalThis.localStorage = dom.window.localStorage
Object.defineProperty(globalThis, 'navigator', {
  value: dom.window.navigator,
  configurable: true,
})
globalThis.requestAnimationFrame = (callback) => setTimeout(callback, 0)
globalThis.IS_REACT_ACT_ENVIRONMENT = true
dom.window.HTMLDialogElement.prototype.showModal = function () {
  this.setAttribute('open', '')
}
const { render, fireEvent, screen, waitFor, cleanup, act } =
  await import('@testing-library/react')
let online = true,
  id = 'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa',
  outletMounts = 0
Object.defineProperty(dom.window.navigator, 'onLine', { get: () => online })
const row = {
  id,
  reference: 'APP-' + 'A'.repeat(32),
  student_name: 'TEST Learner',
  guardian_name: 'TEST Guardian',
  date_of_birth: '2019-02-01',
  grade: 'Grade 1',
  phone: '+263775177935',
  email: 'test@example.invalid',
  address: 'TEST address',
  previous_school: 'TEST previous',
  additional_information: 'TEST information',
  status: 'pending',
  version: 1,
  created_at: '2026-10-13T08:00:00Z',
}
const enquiry = {
  ...row,
  reference: 'ENQ-' + 'B'.repeat(32),
  full_name: 'TEST Visitor',
  subject: 'TEST Subject',
  message: 'TEST full message',
  status: 'new',
}
const paginated = (rows) => ({
  count: rows.length,
  results: rows,
  next: null,
  previous: null,
})
let listMock, detailMock, historyMock, reviewMock, calls
function defaults() {
  calls = []
  listMock = async () => paginated([row])
  detailMock = async (kind) => (kind === 'applications' ? row : enquiry)
  historyMock = async () => paginated([])
  reviewMock = async (kind, recordId, payload) => ({
    ...(kind === 'applications' ? row : enquiry),
    status: payload.status || 'pending',
    version: payload.version + 1,
  })
}
defaults()
const require = createRequire(import.meta.url),
  cache = new Map()
const mocks = {
  'react-router-dom': {
    Link: ({ to, children, ...props }) =>
      React.createElement('a', { href: to, ...props }, children),
    useParams: () => ({ intakeId: id }),
    useLocation: () => ({ pathname: '/school/admissions' }),
    Navigate: ({ to }) => React.createElement('p', null, 'Navigate: ' + to),
    Outlet: () => {
      outletMounts++
      return React.createElement('p', null, 'INTAKE CHILD')
    },
  },
  '../auth/context': { AuthContext },
  './context': { AuthContext },
  '../api/intake': {
    ...actual,
    listIntake: (...args) => listMock(...args),
    getIntake: (...args) => detailMock(...args),
    intakeHistory: (...args) => historyMock(...args),
    reviewIntake: (...args) => {
      calls.push(args)
      return reviewMock(...args)
    },
  },
}
globalThis.intakeTestMocks = mocks
const dataUrl = (code) =>
  `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
async function compile(url) {
  if (cache.has(url.href)) return cache.get(url.href)
  const transformed = await transformWithOxc(
    await readFile(url, 'utf8'),
    url.pathname,
    { jsx: { runtime: 'automatic' } },
  )
  let code = transformed.code
  for (const match of [...code.matchAll(/from (["'])([^"']+)\1/g)]) {
    const specifier = match[2]
    let resolved
    if (mocks[specifier])
      resolved = dataUrl(
        Object.keys(mocks[specifier])
          .map(
            (key) =>
              `export const ${key} = globalThis.intakeTestMocks[${JSON.stringify(specifier)}][${JSON.stringify(key)}];`,
          )
          .join('\n'),
      )
    else if (specifier.startsWith('.')) {
      const relative = new URL(/\.(js|jsx)$/.test(specifier) ? specifier : specifier + '.js', url)
      resolved = relative.pathname.endsWith('.jsx') ? await compile(relative) : relative.href
    }
    else resolved = pathToFileURL(require.resolve(specifier)).href
    code = code.replace(match[0], `from ${JSON.stringify(resolved)}`)
  }
  const result = dataUrl(code)
  cache.set(url.href, result)
  return result
}
const { default: List } = await import(
  await compile(new URL('./pages/IntakeListPage.jsx', import.meta.url))
)
const { default: Detail } = await import(
  await compile(new URL('./pages/IntakeDetailPage.jsx', import.meta.url))
)
const { default: Boundary } = await import(
  await compile(
    new URL('./components/IntakeOnlineBoundary.jsx', import.meta.url),
  )
)
const { default: ProtectedRoute } = await import(
  await compile(new URL('./auth/ProtectedRoute.jsx', import.meta.url))
)
afterEach(() => {
  cleanup()
  defaults()
  online = true
  id = row.id
  sessionStorage.clear()
  localStorage.clear()
  setAuthenticationFailureHandler(() => {})
})
after(() => dom.window.close())

test('existing route guard allows only school administrators', () => {
  for (const [user, destination] of [
    [null, '/login'],
    [{ role: 'parent' }, '/parent'],
    [{ role: 'platform_admin' }, '/platform'],
    [{ role: 'school_admin', must_change_password: true }, '/change-password'],
  ]) {
    render(
      React.createElement(
        AuthContext.Provider,
        { value: { user, isLoading: false } },
        React.createElement(ProtectedRoute, { allowedRole: 'school_admin' }),
      ),
    )
    assert.ok(screen.getByText('Navigate: ' + destination))
    cleanup()
  }
  render(
    React.createElement(
      AuthContext.Provider,
      { value: { user: { role: 'school_admin' }, isLoading: false } },
      React.createElement(ProtectedRoute, { allowedRole: 'school_admin' }),
    ),
  )
  assert.ok(screen.getByText('INTAKE CHILD'))
})
test('list, current-page search, status filter and server pagination', async () => {
  const requests = []
  listMock = async (kind, options) => {
    requests.push([kind, options])
    return {
      ...paginated(options.page === 2 ? [] : [row]),
      count: 26,
      next: options.page === 1 ? 'http://untrusted.invalid/page2' : null,
      previous: options.page === 2 ? 'page1' : null,
    }
  }
  render(React.createElement(List, { kind: 'applications' }))
  await screen.findByText(row.student_name)
  fireEvent.change(screen.getByRole('searchbox'), {
    target: { value: 'unmatched' },
  })
  assert.ok(screen.getByText(/No matches on this page/))
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'APP-' } })
  assert.ok(screen.getByText(row.student_name))
  fireEvent.click(
    screen.getByRole('button', { name: 'Next page', exact: true }),
  )
  await waitFor(() => assert.equal(requests.at(-1)[1].page, 2))
  fireEvent.change(screen.getByLabelText('Status'), {
    target: { value: 'rejected' },
  })
  await waitFor(() => assert.equal(requests.at(-1)[1].status, 'rejected'))
  assert.equal(requests.at(-1)[1].page, 1)
})
test('empty list and backend loading failure are separate states', async () => {
  listMock = async () => paginated([])
  render(React.createElement(List, { kind: 'applications' }))
  await screen.findByText(/No admissions are available/)
  cleanup()
  listMock = async () => {
    throw { status: 503 }
  }
  render(React.createElement(List, { kind: 'enquiries' }))
  assert.match(
    (await screen.findByRole('alert')).textContent,
    /could not be confirmed/,
  )
  assert.equal(Boolean(screen.queryByText(/No enquiries are available/)), false)
})
test('application detail shows fields; cancelled confirmation makes no request', async () => {
  render(React.createElement(Detail, { kind: 'applications' }))
  await screen.findByText(row.student_name)
  for (const value of [
    row.guardian_name,
    row.date_of_birth,
    row.email,
    row.address,
    row.previous_school,
    row.additional_information,
  ])
    assert.ok(screen.getByText(value))
  fireEvent.click(screen.getByRole('button', { name: 'Approve Application' }))
  assert.ok(screen.getByRole('dialog'))
  fireEvent.click(screen.getByRole('button', { name: 'Cancel', exact: true }))
  assert.equal(calls.length, 0)
})
test('approval waits for backend, records note/version, and blocks repeated clicks', async () => {
  let release
  reviewMock = () => new Promise((resolve) => (release = resolve))
  render(React.createElement(Detail, { kind: 'applications' }))
  await screen.findByText(row.student_name)
  fireEvent.change(screen.getByLabelText('Internal review note'), {
    target: { value: 'TEST private review' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Approve Application' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm review' }))
  assert.equal(screen.getByRole('button', { name: 'Saving...' }).disabled, true)
  fireEvent.click(screen.getByRole('button', { name: 'Saving...' }))
  assert.equal(calls.length, 1)
  assert.deepEqual(calls[0].slice(0, 3), [
    'applications',
    id,
    { version: 1, status: 'approved', note: 'TEST private review' },
  ])
  assert.equal(
    Boolean(screen.queryByText('Review saved by the backend.')),
    false,
  )
  await act(async () => release({ ...row, status: 'approved', version: 2 }))
  await screen.findByText('Review saved by the backend.')
  assert.ok(screen.getByText('Approved'))
})
test('rejection and notes-only updates use existing review schema', async () => {
  render(React.createElement(Detail, { kind: 'applications' }))
  await screen.findByText(row.student_name)
  fireEvent.click(screen.getByRole('button', { name: 'Reject Application' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm review' }))
  await screen.findByText('Review saved by the backend.')
  assert.equal(calls[0][2].status, 'rejected')
  fireEvent.change(screen.getByLabelText('Internal review note'), {
    target: { value: 'TEST note only' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Save review note' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm review' }))
  await waitFor(() => assert.equal(calls.length, 2))
  assert.equal(calls[1][2].status, null)
  assert.equal(calls[1][2].version, 2)
})
test('enquiry full message, statuses, handling note and history', async () => {
  historyMock = async () =>
    paginated([
      {
        id: 9,
        actor_id: 2,
        from_status: 'new',
        to_status: 'in_progress',
        note: 'TEST history note',
        version: 2,
        created_at: row.created_at,
      },
    ])
  render(React.createElement(Detail, { kind: 'enquiries' }))
  await screen.findByText(enquiry.message)
  await screen.findByText('TEST history note')
  fireEvent.change(screen.getByLabelText('Status'), {
    target: { value: 'resolved' },
  })
  fireEvent.change(screen.getByLabelText('Internal handling note'), {
    target: { value: 'TEST handled' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Save enquiry update' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm review' }))
  await screen.findByText('Review saved by the backend.')
  assert.equal(calls[0][2].status, 'resolved')
})
test('409 requires reload, clears draft, and displays fresh version before retry', async () => {
  reviewMock = async () => {
    throw { status: 409 }
  }
  render(React.createElement(Detail, { kind: 'applications' }))
  await screen.findByText(row.student_name)
  fireEvent.change(screen.getByLabelText('Internal review note'), {
    target: { value: 'TEST stale draft' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Approve Application' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm review' }))
  assert.match(
    (await screen.findByRole('alert')).textContent,
    /Another administrator/,
  )
  assert.equal(
    screen.getByRole('button', { name: 'Approve Application' }).disabled,
    true,
  )
  detailMock = async () => ({ ...row, status: 'rejected', version: 3 })
  fireEvent.click(screen.getByRole('button', { name: 'Reload latest record' }))
  await screen.findByText('Rejected')
  assert.equal(screen.getByLabelText('Internal review note').value, '')
  assert.equal(
    screen.getByRole('button', { name: 'Approve Application' }).disabled,
    false,
  )
})
test('lost review response cannot show success and requires reload', async () => {
  reviewMock = async () => {
    throw { code: 'network_error' }
  }
  render(React.createElement(Detail, { kind: 'applications' }))
  await screen.findByText(row.student_name)
  fireEvent.click(screen.getByRole('button', { name: 'Approve Application' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm review' }))
  await screen.findByRole('alert')
  assert.equal(
    Boolean(screen.queryByText('Review saved by the backend.')),
    false,
  )
  assert.equal(
    screen.getByRole('button', { name: 'Approve Application' }).disabled,
    true,
  )
})
test('offline boundary unmounts sensitive views; reconnect remounts fresh views', async () => {
  outletMounts = 0
  render(
    React.createElement(
      AuthContext.Provider,
      { value: { user: { id: 1 } } },
      React.createElement(Boundary),
    ),
  )
  assert.ok(screen.getByText('INTAKE CHILD'))
  online = false
  fireEvent(window, new window.Event('offline'))
  assert.ok(screen.getByText('Online connection required'))
  assert.equal(Boolean(screen.queryByText('INTAKE CHILD')), false)
  online = true
  fireEvent(window, new window.Event('online'))
  assert.ok(screen.getByText('INTAKE CHILD'))
  assert.equal(outletMounts, 2)
})
test('existing authenticated client sends exact routes/no-store and no school ID; offline requests are rejected', async () => {
  const requests = []
  tokenStorage.setTokens({ access: 'TEST_ACCESS', refresh: 'TEST_REFRESH' })
  globalThis.fetch = async (url, options) => {
    requests.push([url, options])
    return { status: 200, ok: true, json: async () => paginated([row]) }
  }
  await actual.listIntake('applications', { page: 2, status: 'pending' })
  await actual.reviewIntake('enquiries', id, {
    version: 1,
    status: 'resolved',
    note: 'TEST note',
    school: 99,
  })
  assert.match(
    requests[0][0],
    /\/school\/applications\/\?page=2&status=pending$/,
  )
  assert.equal(requests[0][1].cache, 'no-store')
  assert.equal(
    requests[0][1].headers.get('Authorization'),
    'Bearer TEST_ACCESS',
  )
  assert.deepEqual(JSON.parse(requests[1][1].body), {
    version: 1,
    status: 'resolved',
    note: 'TEST note',
  })
  online = false
  await assert.rejects(actual.listIntake('applications'))
  assert.equal(requests.length, 2)
  assert.equal((await queuedOperations('intake-test')).length, 0)
  assert.equal(await cachedValue('intake-test', 'intake'), null)
  assert.equal(localStorage.length, 0)
  assert.equal(sessionStorage.length, 2)
})
test('expired JWT uses existing refresh failure handler and clears tokens', async () => {
  tokenStorage.setTokens({ access: 'EXPIRED_TEST', refresh: 'EXPIRED_REFRESH' })
  let expired = false
  setAuthenticationFailureHandler(() => {
    expired = true
  })
  globalThis.fetch = async () => ({
    status: 401,
    ok: false,
    json: async () => ({ detail: 'Expired test token' }),
  })
  await assert.rejects(
    actual.getIntake('applications', id),
    (error) => error.code === 'session_expired',
  )
  assert.equal(expired, true)
  assert.equal(sessionStorage.length, 0)
})

test('invalid record IDs and filters reject safely without requests', async () => {
  let calls = 0
  globalThis.fetch = async () => {
    calls++
    throw new Error('Must not be called')
  }
  await assert.rejects(actual.getIntake('applications', 'not-a-uuid'))
  await assert.rejects(actual.listIntake('enquiries', { status: 'approved' }))
  await assert.rejects(actual.listIntake('applications', { page: -1 }))
  assert.equal(calls, 0)
})
