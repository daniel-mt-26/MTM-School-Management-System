import 'fake-indexeddb/auto'
import assert from 'node:assert/strict'
import test from 'node:test'

import {
  cacheValue, cachedValue, clearOfflineScope, discardOperation, enqueueOperation, queuedOperations, syncMetadata,
} from './db.js'
import { processSyncQueue } from './sync.js'
import { cacheInventory, cachedInventory, inventoryWithLocalChanges, localId, queueInventoryCreate, queueInventoryMovement } from './inventory.js'
import { attendanceWithLocalChanges, cacheAttendanceRoster, cachedAttendanceRoster, queueAttendanceBulk } from './attendance.js'
import { cacheHomework, cachedHomework, homeworkWithLocalChanges, queueHomework } from './homework.js'

function operation(index) {
  return {
    module: 'inventory', entity: 'category', entityId: null, action: 'create', method: 'POST',
    path: '/school/inventory/categories/', payload: { name: `Category ${index}` },
  }
}

test('queue persists records in creation order and marks successful operations complete', async () => {
  const scope = `test:${crypto.randomUUID()}`
  await enqueueOperation(scope, operation(1))
  await enqueueOperation(scope, operation(2))
  const pending = await queuedOperations(scope)
  assert.equal(pending.length, 2)
  const sent = []
  await processSyncQueue(scope, { force: true, send: async (record) => { sent.push(record.payload.name) } })
  assert.deepEqual(sent, ['Category 1', 'Category 2'])
  assert.equal((await queuedOperations(scope)).length, 0)
  assert.ok((await syncMetadata(scope)).lastSyncedAt)
  await clearOfflineScope(scope)
})

test('failed operations remain queued with a safe failure category', async () => {
  const scope = `test:${crypto.randomUUID()}`
  await enqueueOperation(scope, operation(1))
  const error = new Error('offline')
  error.code = 'network_error'
  await processSyncQueue(scope, { force: true, send: async () => { throw error } })
  const failed = await queuedOperations(scope)
  assert.equal(failed.length, 1)
  assert.equal(failed[0].status, 'failed')
  assert.equal(failed[0].retryCount, 1)
  assert.equal(failed[0].failureCategory, 'network')
  await clearOfflineScope(scope)
})

test('clearing an account scope removes cached data and pending work', async () => {
  const scope = `test:${crypto.randomUUID()}`
  await cacheValue(scope, 'inventory:items', [{ id: 1 }])
  await enqueueOperation(scope, operation(1))
  assert.deepEqual(await cachedValue(scope, 'inventory:items'), [{ id: 1 }])
  await clearOfflineScope(scope)
  assert.equal(await cachedValue(scope, 'inventory:items'), null)
  assert.equal((await queuedOperations(scope)).length, 0)
})

test('cached inventory is tenant-scoped and queued movement produces provisional stock', async () => {
  const firstScope = `test:${crypto.randomUUID()}`
  const secondScope = `test:${crypto.randomUUID()}`
  await cacheInventory(firstScope, {
    categories: [{ id: 1, name: 'Uniforms', is_active: true }],
    items: [{ id: 2, category: 1, category_name: 'Uniforms', name: 'School Shirt', unit: 'each', minimum_stock_level: 3, available_stock: 10, stock_status: 'in_stock', variants: [], is_active: true }],
    variants: [], movements: [], summary: {},
  })
  await queueInventoryMovement(firstScope, { item: 2, variant: null, movement_type: 'issued', direction: 'out', quantity: 2, notes: '' })
  const display = await inventoryWithLocalChanges(firstScope, await cachedInventory(firstScope))
  assert.equal(display.items[0].available_stock, 8)
  assert.equal(display.movements[0].syncStatus, 'pending')
  assert.equal(await cachedInventory(secondScope), null)
  await clearOfflineScope(firstScope)
})

test('local category and item creations map IDs and preserve dependency order', async () => {
  const scope = `test:${crypto.randomUUID()}`
  const category = await queueInventoryCreate(scope, 'category', { name: 'Books', description: '' })
  await queueInventoryCreate(scope, 'item', { category: category.localId, name: 'Exercise book', code: '', description: '', unit: 'each', minimum_stock_level: 0, cost_per_unit: null, storage_location: '' })
  const sent = []
  await processSyncQueue(scope, { force: true, send: async (record) => {
    sent.push(record)
    return record.entity === 'category' ? { id: 41 } : { id: 42 }
  } })
  assert.equal(sent.length, 2)
  assert.equal(sent[1].payload.category, 41)
  assert.equal((await queuedOperations(scope)).length, 0)
  await clearOfflineScope(scope)
})

test('server rejection remains a sync issue, preserves its idempotency key, and can be discarded', async () => {
  const scope = `test:${crypto.randomUUID()}`
  const movement = await queueInventoryMovement(scope, { item: 9, variant: null, movement_type: 'issued', direction: 'out', quantity: 5, notes: '' })
  const error = new Error('insufficient stock')
  error.status = 400; error.data = { quantity: ['Only 3 items are currently available on the server.'] }
  let submittedId
  await processSyncQueue(scope, { force: true, send: async (record) => { submittedId = record.id; throw error } })
  const failed = await queuedOperations(scope)
  assert.equal(submittedId, movement.id)
  assert.equal(failed[0].status, 'failed')
  assert.equal(failed[0].failureCategory, 'validation')
  assert.match(failed[0].failureMessage, /Only 3 items/)
  await discardOperation(movement.id)
  assert.equal((await queuedOperations(scope)).length, 0)
  await clearOfflineScope(scope)
})

test('authentication expiry preserves queued work and blocks dependent local records', async () => {
  const scope = `test:${crypto.randomUUID()}`
  const category = await queueInventoryCreate(scope, 'category', { name: 'Stationery', description: '' })
  await queueInventoryCreate(scope, 'item', { category: localId(category.id), name: 'Pencil', code: '', description: '', unit: 'each', minimum_stock_level: 0, cost_per_unit: null, storage_location: '' })
  const error = new Error('session expired'); error.code = 'session_expired'
  await processSyncQueue(scope, { force: true, send: async () => { throw error } })
  const pending = await queuedOperations(scope)
  assert.equal(pending.length, 2)
  assert.equal(pending[0].failureCategory, 'authentication')
  assert.equal(pending[1].status, 'pending')
  await clearOfflineScope(scope)
})

test('attendance roster is cached and an offline class save survives as pending local state', async () => {
  const scope = `test:${crypto.randomUUID()}`
  const context = { school_class: 1, academic_year: 2, term: 3, attendance_date: '2026-09-20' }
  await cacheAttendanceRoster(scope, { ...context, class_name: 'Grade 3 Blue', students: [{ enrollment: 9, student: 8, display_name: 'Tariro Moyo', admission_number: 'A-01', attendance: null }] })
  const operation = await queueAttendanceBulk(scope, { ...context, entries: [{ enrollment: 9, status: 'absent', last_known_updated_at: null }] })
  const display = await attendanceWithLocalChanges(scope, await cachedAttendanceRoster(scope, context))
  assert.equal(display.students[0].attendance.status, 'absent')
  assert.equal(display.students[0].syncStatus, 'pending')
  const sent = []
  await processSyncQueue(scope, { force: true, send: async (record) => { sent.push(record.id); return { created: 1 } } })
  assert.deepEqual(sent, [operation.id])
  await clearOfflineScope(scope)
})

test('homework cache keeps reference data and queued text homework is provisional', async () => {
  const scope = `test:${crypto.randomUUID()}`
  await cacheHomework(scope, { items: [], classes: [{ id: 1, name: 'Grade 3' }], subjects: [{ id: 2, name: 'Maths' }] })
  const operation = await queueHomework(scope, { title: 'Fractions', instructions: 'Complete questions 1-5.', school_class: 1, subject: 2, date_assigned: '2026-09-20', due_date: '2026-09-21', status: 'draft' })
  const display = await homeworkWithLocalChanges(scope, await cachedHomework(scope))
  assert.equal(display.items[0].id, `local:${operation.id}`)
  assert.equal(display.items[0].syncStatus, 'pending')
  await clearOfflineScope(scope)
})

test('mixed queue resumes safely after connectivity fails between operations', async () => {
  const scope = `test:${crypto.randomUUID()}`
  const inventory = await enqueueOperation(scope, operation(1))
  const homework = await queueHomework(scope, { title: 'Reading', instructions: '', school_class: 1, subject: null, date_assigned: '2026-09-20', due_date: '2026-09-21', status: 'draft' })
  const sent = []
  const network = new Error('offline'); network.code = 'network_error'
  await processSyncQueue(scope, { force: true, send: async (record) => { sent.push(record.id); if (record.id === homework.id) throw network; return { id: 90 } } })
  assert.deepEqual(sent, [inventory.id, homework.id])
  const remaining = await queuedOperations(scope)
  assert.equal(remaining.length, 1)
  assert.equal(remaining[0].id, homework.id)
  await processSyncQueue(scope, { force: true, send: async (record) => { sent.push(record.id); return { id: 91 } } })
  assert.deepEqual(sent, [inventory.id, homework.id, homework.id])
  assert.equal((await queuedOperations(scope)).length, 0)
  await clearOfflineScope(scope)
})
