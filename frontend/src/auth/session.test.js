import assert from 'node:assert/strict'
import test from 'node:test'

import { createSingleFlight } from './session.js'

function response(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function installSessionStorage(values = {}) {
  const store = new Map(Object.entries(values))
  globalThis.sessionStorage = {
    getItem: (key) => store.get(key) ?? null,
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: (key) => store.delete(key),
  }
  return store
}

test('a login or startup user load shares one in-progress /me request', async () => {
  let calls = 0
  let resolveRequest
  const loadUser = createSingleFlight(() => {
    calls += 1
    return new Promise((resolve) => { resolveRequest = resolve })
  })

  const first = loadUser()
  const second = loadUser()
  await Promise.resolve()
  assert.equal(calls, 1)
  assert.strictEqual(first, second)
  resolveRequest({ id: 1, username: 'administrator' })
  assert.deepEqual(await first, { id: 1, username: 'administrator' })
})

test('authenticated profile requests use the access token', async () => {
  installSessionStorage({ mtm_access_token: 'access-token', mtm_refresh_token: 'refresh-token' })
  const requests = []
  globalThis.fetch = async (url, options) => {
    requests.push({ url, authorization: new Headers(options.headers).get('Authorization') })
    return response({ name: 'School' })
  }
  const { apiClient } = await import('../api/client.js')
  await apiClient('/school/profile/')
  assert.deepEqual(requests, [{ url: 'http://127.0.0.1:8000/api/school/profile/', authorization: 'Bearer access-token' }])
})

test('a /me 401 makes one refresh attempt and never retries continuously', async () => {
  const store = installSessionStorage({ mtm_access_token: 'expired-access', mtm_refresh_token: 'refresh-token' })
  const requests = []
  globalThis.fetch = async (url, options) => {
    requests.push({ url, authorization: new Headers(options.headers).get('Authorization') })
    if (url.endsWith('/auth/token/refresh/')) return response({ access: 'new-access' })
    return response({ detail: 'Unauthorized' }, 401)
  }
  const { apiClient } = await import('../api/client.js')
  await assert.rejects(apiClient('/auth/me/'), (error) => error.code === 'session_expired')
  assert.equal(requests.filter((item) => item.url.endsWith('/auth/me/')).length, 2)
  assert.equal(requests.filter((item) => item.url.endsWith('/auth/token/refresh/')).length, 1)
  assert.equal(store.get('mtm_access_token'), undefined)
  assert.equal(store.get('mtm_refresh_token'), undefined)
})

test('a public health request sends no authorization header', async () => {
  installSessionStorage({ mtm_access_token: 'access-token' })
  let authorization
  globalThis.fetch = async (_url, options) => {
    authorization = new Headers(options.headers).get('Authorization')
    return response({ status: 'ok' })
  }
  const { apiClient } = await import('../api/client.js')
  await apiClient('/health/', { authenticate: false, cache: 'no-store' })
  assert.equal(authorization, null)
})

test('simultaneous dashboard mounts share one school profile request', async () => {
  installSessionStorage({ mtm_access_token: 'access-token' })
  let calls = 0
  let resolveRequest
  globalThis.fetch = async () => {
    calls += 1
    return new Promise((resolve) => { resolveRequest = resolve })
  }
  const { getSchoolProfile } = await import('../api/school.js')
  const first = getSchoolProfile()
  const second = getSchoolProfile()
  assert.strictEqual(first, second)
  assert.equal(calls, 1)
  resolveRequest(response({ name: 'School' }))
  await first
})
