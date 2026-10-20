// Run only against an isolated backend with synthetic fixtures, never production.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { createRequire } from 'node:module'
const require = createRequire(import.meta.url)
const { chromium } = require(process.argv[2])
const { default: AxeBuilder } = require(process.argv[3])
const fixture = JSON.parse(fs.readFileSync(process.argv[4], 'utf8'))
const base = process.env.INTAKE_TEST_FRONTEND || 'http://127.0.0.1:4176'
const api = process.env.INTAKE_TEST_API || 'http://127.0.0.1:8053/api'
const refreshed = await fetch(`${api}/auth/token/refresh/`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ refresh: fixture.admin.refresh }),
})
assert.equal(refreshed.status, 200, 'Synthetic test token refresh')
Object.assign(fixture.admin, await refreshed.json())
const browser = await chromium.launch({
  executablePath:
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  headless: true,
})
const passed = [],
  runtimeErrors = []
const run = Date.now().toString()
const approvalNote = `TEST browser approval note ${run}`
const concurrentNote = `TEST concurrent administrator update ${run}`
let scans = 0
try {
  const anonymous = await browser.newPage()
  await anonymous.goto(base + '/school/admissions')
  await anonymous.waitForURL('**/login')
  await anonymous.close()
  passed.push('Unauthenticated route rejection')
  const context = await browser.newContext()
  await context.addInitScript((tokens) => {
    sessionStorage.setItem('mtm_access_token', tokens.access)
    sessionStorage.setItem('mtm_refresh_token', tokens.refresh)
  }, fixture.admin)
  const initial = await context.request.get(
    `${api}/school/applications/${fixture.applicationId}/`,
    { headers: { Authorization: `Bearer ${fixture.admin.access}` } },
  )
  assert.equal(initial.status(), 200)
  const initialRecord = await initial.json()
  if (initialRecord.status !== 'pending') {
    const reset = await context.request.post(
      `${api}/school/applications/${fixture.applicationId}/review/`,
      {
        headers: { Authorization: `Bearer ${fixture.admin.access}` },
        data: {
          version: initialRecord.version,
          status: 'pending',
          note: `TEST fixture reset ${run}`,
        },
      },
    )
    assert.equal(reset.status(), 200)
  }
  const page = await context.newPage()
  page.on('pageerror', (error) => runtimeErrors.push(error.message))
  async function scan(label) {
    const result = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .analyze()
    assert.deepEqual(
      result.violations.map((v) => ({
        id: v.id,
        nodes: v.nodes.map((n) => n.target),
      })),
      [],
      label,
    )
    scans++
  }
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(base + '/school')
  await page.getByRole('link', { name: /Admissions Review online/ }).waitFor()
  await page.getByRole('link', { name: /Enquiries Manage contact/ }).waitFor()
  passed.push('Existing School Dashboard navigation')
  await page.goto(base + '/school/admissions')
  await page
    .getByRole('link', { name: fixture.applicationReference, exact: true })
    .waitFor()
  assert.equal(await page.getByText('TEST PRIVATE OTHER SCHOOL').count(), 0)
  await page.getByRole('searchbox').fill('TEST Phase 3 learner')
  assert.equal(await page.locator('tbody tr').count(), 1)
  await scan('Desktop admissions list')
  await page
    .getByRole('link', { name: fixture.applicationReference, exact: true })
    .click()
  await page.getByText('TEST Phase 3 learner', { exact: true }).waitFor()
  await page.getByLabel('Internal review note').fill(approvalNote)
  await page.getByRole('button', { name: 'Approve Application' }).click()
  await page.getByRole('dialog').waitFor()
  await scan('Confirmation dialog')
  assert.equal(
    await page
      .getByRole('button', { name: 'Cancel', exact: true })
      .evaluate((e) => e === document.activeElement),
    true,
  )
  await page.keyboard.press('Escape')
  assert.equal(await page.locator('dialog').count(), 0)
  assert.equal(
    await page
      .getByRole('button', { name: 'Approve Application' })
      .evaluate((e) => e === document.activeElement),
    true,
  )
  await page.getByRole('button', { name: 'Approve Application' }).click()
  await page.getByRole('button', { name: 'Confirm review' }).click()
  await page
    .getByText('Review saved by the backend.', { exact: true })
    .waitFor()
  await page.getByText(approvalNote, { exact: true }).waitFor()
  const appAfter = await context.request.get(
    `${api}/school/applications/${fixture.applicationId}/`,
    { headers: { Authorization: `Bearer ${fixture.admin.access}` } },
  )
  assert.equal(appAfter.status(), 200)
  assert.equal((await appAfter.json()).status, 'approved')
  passed.push(
    'Real authenticated approval, internal note/history and keyboard cancellation',
  )
  // Change the record through the same real API after the browser loaded its version.
  const latest = await appAfter.json()
  const externalReview = await context.request.post(
    `${api}/school/applications/${fixture.applicationId}/review/`,
    {
      headers: { Authorization: `Bearer ${fixture.admin.access}` },
      data: { version: latest.version, note: concurrentNote },
    },
  )
  assert.equal(externalReview.status(), 200)
  await page.getByRole('button', { name: 'Reject Application' }).click()
  await page.getByRole('button', { name: 'Confirm review' }).click()
  await page
    .getByRole('alert')
    .filter({ hasText: 'Another administrator' })
    .waitFor()
  assert.equal(
    await page.getByRole('button', { name: 'Reject Application' }).isDisabled(),
    true,
  )
  await page.getByRole('button', { name: 'Reload latest record' }).click()
  await page.getByText(concurrentNote, { exact: true }).waitFor()
  await page.getByRole('button', { name: 'Reject Application' }).click()
  await page.getByRole('button', { name: 'Confirm review' }).click()
  await page
    .getByText('Review saved by the backend.', { exact: true })
    .waitFor()
  passed.push('Real 409 conflict, explicit reload, confirmed rejection')
  await page.goto(`${base}/school/enquiries/${fixture.enquiryId}`)
  await page.getByText('TEST Phase 3 full message', { exact: true }).waitFor()
  for (const status of ['in_progress', 'resolved', 'new']) {
    await page.getByLabel('Status', { exact: true }).selectOption(status)
    await page
      .getByLabel('Internal handling note')
      .fill(`TEST handling ${status} ${run}`)
    await page.getByRole('button', { name: 'Save enquiry update' }).click()
    await page.getByRole('button', { name: 'Confirm review' }).click()
    await page
      .getByText('Review saved by the backend.', { exact: true })
      .waitFor()
    await page.locator('dialog').waitFor({ state: 'detached' })
    await page
      .getByText(`TEST handling ${status} ${run}`, { exact: true })
      .waitFor()
  }
  passed.push('Real enquiry statuses, full message and handling history')
  for (const width of [320, 375, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
      false,
    )
    await scan('Detail width ' + width)
    await page.screenshot({
      path: path.join(process.env.TEMP, `mtm-intake-detail-${width}.png`),
      fullPage: true,
    })
  }
  await page.goto(base + '/school/enquiries')
  await page.getByRole('link', { name: fixture.enquiryReference }).waitFor()
  await page.setViewportSize({ width: 375, height: 900 })
  await scan('Mobile enquiry list')
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
    false,
  )
  const stores = await page.evaluate(async () => {
    const results = []
    for (const entry of await indexedDB.databases()) {
      const db = await new Promise((resolve, reject) => {
        const request = indexedDB.open(entry.name)
        request.onsuccess = () => resolve(request.result)
        request.onerror = reject
      })
      for (const name of ['offline_cache', 'sync_queue'])
        if (db.objectStoreNames.contains(name)) {
          const rows = await new Promise((resolve, reject) => {
            const request = db.transaction(name).objectStore(name).getAll()
            request.onsuccess = () => resolve(request.result)
            request.onerror = reject
          })
          results.push(...rows)
        }
      db.close()
    }
    return JSON.stringify(results)
  })
  assert.equal(stores.includes('TEST Phase 3'), false)
  assert.equal(
    await page.evaluate(async () => {
      for (const name of await caches.keys()) {
        const cache = await caches.open(name)
        if (
          (await cache.keys()).some((request) =>
            /\/api\/school\/(applications|enquiries)\//.test(request.url),
          )
        )
          return true
      }
      return false
    }),
    false,
  )
  assert.equal(
    await page.evaluate(() =>
      JSON.stringify(Object.values(localStorage)).includes('TEST Phase 3'),
    ),
    false,
  )
  assert.equal(
    await page.evaluate(() =>
      JSON.stringify(Object.values(sessionStorage)).includes('TEST Phase 3'),
    ),
    false,
  )
  await context.setOffline(true)
  await page
    .getByRole('heading', { name: 'Online connection required' })
    .waitFor()
  assert.equal(
    await page.getByRole('link', { name: fixture.enquiryReference }).count(),
    0,
  )
  await context.setOffline(false)
  await page.getByRole('link', { name: fixture.enquiryReference }).waitFor()
  passed.push(
    'Responsive views, online-only state clearing, no intake in browser stores/queue',
  )
  const denied = await context.request.get(
    `${api}/school/applications/${fixture.foreignId}/`,
    { headers: { Authorization: `Bearer ${fixture.admin.access}` } },
  )
  assert.equal(denied.status(), 404)
  await page.goto(`${base}/school/admissions/${fixture.foreignId}`)
  await page
    .getByRole('alert')
    .filter({ hasText: 'does not belong to your school' })
    .waitFor()
  assert.equal(await page.getByText('TEST PRIVATE OTHER SCHOOL').count(), 0)
  passed.push('Real cross-school API/detail rejection')
  await page.goto(`${base}/school/admissions/${fixture.applicationId}`)
  await page.getByText('TEST Phase 3 learner', { exact: true }).waitFor()
  // Session expiry responses are mocked only in this browser test.
  await page.route('**/api/school/applications/**', (r) =>
    r.fulfill({
      status: 401,
      contentType: 'application/json',
      body: '{"detail":"Expired test session"}',
    }),
  )
  await page.route('**/api/auth/token/refresh/', (r) =>
    r.fulfill({
      status: 401,
      contentType: 'application/json',
      body: '{"detail":"Expired test refresh"}',
    }),
  )
  await page.getByRole('button', { name: 'Reload latest record' }).click()
  await page.waitForURL('**/login')
  assert.equal(
    await page.getByText('TEST Phase 3 learner', { exact: true }).count(),
    0,
  )
  assert.equal(
    await page.evaluate(() => sessionStorage.getItem('mtm_access_token')),
    null,
  )
  passed.push(
    'Expired session uses existing logout and clears authenticated view',
  )
  assert.deepEqual(runtimeErrors, [])
  const serviceWorkerControlled = await page.evaluate(() =>
    Boolean(navigator.serviceWorker?.controller),
  )
  if (process.env.INTAKE_TEST_REQUIRE_SW === 'true')
    assert.equal(
      serviceWorkerControlled,
      true,
      'Production service worker controls the tested page',
    )
  const report = {
    passed,
    accessibilityScans: scans,
    runtimeErrors,
    serviceWorkerControlled,
  }
  fs.writeFileSync(
    path.join(process.env.TEMP, 'mtm-intake-phase3-browser.json'),
    JSON.stringify(report, null, 2),
  )
  console.log(JSON.stringify(report, null, 2))
} finally {
  await browser.close()
}
