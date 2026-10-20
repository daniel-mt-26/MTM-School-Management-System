import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { compareValues, sortRows } from './components/tableSort.js'
import { inactivityState, INACTIVITY_MS, WARNING_MS } from './auth/inactivity.js'
import { routeForRole } from './auth/roleRoutes.js'

test('teacher routes to assigned portal', () => assert.equal(routeForRole('teacher'), '/teacher'))
test('sorting names, admission numbers, dates, amounts and percentages', () => {
  assert.deepEqual(sortRows([100, 11, 2], x => x), [2, 11, 100])
  assert.deepEqual(sortRows([100, 11, 2], x => x, 'desc'), [100, 11, 2])
  assert.deepEqual(sortRows(['Beth', 'alice'], x => x), ['alice', 'Beth'])
  assert.ok(compareValues('A-2', 'A-11') < 0)
  assert.ok(compareValues('2025-12-31', '2026-01-01') < 0)
  assert.ok(compareValues('$11.00', '$100.00') < 0)
  assert.ok(compareValues('2%', '11%') < 0)
  const filtered = [{ name: 'Zed', keep: true }, { name: 'Amy', keep: true }]
  const sorted = sortRows(filtered, r => r.name)
  assert.equal(filtered[0].name, 'Zed'); assert.equal(sorted[0].name, 'Amy')
})
test('inactivity thresholds use the injected clock', () => {
  assert.equal(inactivityState(0, INACTIVITY_MS - WARNING_MS - 1).warning, false)
  assert.equal(inactivityState(0, INACTIVITY_MS - WARNING_MS).warning, true)
  assert.equal(inactivityState(0, INACTIVITY_MS).expired, true)
  assert.equal(inactivityState(INACTIVITY_MS, INACTIVITY_MS).remaining, INACTIVITY_MS)
})
test('teacher navigation contains allowed tools and excludes finance', () => {
  const source = readFileSync(new URL('./pages/TeacherPortal.jsx', import.meta.url), 'utf8')
  for (const label of ['My Classes', 'Attendance', 'Homework', 'Results', 'Report Comments', 'Timetable', 'Announcements', 'Resources', 'Profile']) assert.ok(source.includes(label))
  assert.ok(!source.includes('/school/finance'))
})
test('attribution safely links to MDS', () => {
  const source = readFileSync(new URL('./components/Attribution.jsx', import.meta.url), 'utf8')
  for (const value of ['Powered by MDS', 'https://www.mtmdigitalsolutions.co.zw/', 'target="_blank"', 'rel="noopener noreferrer"']) assert.ok(source.includes(value))
})

test('queued work cannot be sent under a different authenticated account', async () => {
  const { setApplicationRole } = await import('./api/client.js')
  const { sendQueuedOperation } = await import('./offline/sync.js')
  let sends = 0
  const prior = globalThis.fetch
  globalThis.fetch = async () => { sends++; throw new Error('Unexpected send') }
  setApplicationRole('teacher', 100)
  try {
    await assert.rejects(sendQueuedOperation({ scope: 'user:99:teacher', path: '/teacher/homework/', method: 'POST', payload: { title: 'Private draft' } }), error => error.code === 'session_expired')
    assert.equal(sends, 0)
  } finally { setApplicationRole(null); globalThis.fetch = prior }
})
