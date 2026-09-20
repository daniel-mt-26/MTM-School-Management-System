import { openDB } from 'idb'

const DATABASE_NAME = 'mtm-offline'
const DATABASE_VERSION = 2

function scopedKey(scope, key) {
  return `${scope}:${key}`
}

export function accountScope(user) {
  return user ? `user:${user.id}:${user.role}` : null
}

async function database() {
  return openDB(DATABASE_NAME, DATABASE_VERSION, {
    upgrade(db, oldVersion) {
      if (oldVersion > 0) return
      const cache = db.createObjectStore('offline_cache', { keyPath: 'key' })
      cache.createIndex('scope', 'scope')
      const queue = db.createObjectStore('sync_queue', { keyPath: 'id' })
      queue.createIndex('scope', 'scope')
      queue.createIndex('scope_status', ['scope', 'status'])
      queue.createIndex('scope_created', ['scope', 'createdAt'])
      const metadata = db.createObjectStore('sync_metadata', { keyPath: 'key' })
      metadata.createIndex('scope', 'scope')
    },
  })
}

function assertSafePayload(payload) {
  const prohibited = /password|token|authorization|secret|database[_-]?url|supabase/i
  const keys = []
  const visit = (value) => {
    if (!value || typeof value !== 'object') return
    Object.entries(value).forEach(([key, child]) => { keys.push(key); visit(child) })
  }
  visit(payload)
  if (keys.some((key) => prohibited.test(key))) throw new Error('Queued payload contains a prohibited field.')
}

export async function cacheValue(scope, key, value) {
  const db = await database()
  await db.put('offline_cache', { key: scopedKey(scope, key), scope, value, updatedAt: new Date().toISOString() })
}

export async function cachedValue(scope, key) {
  const db = await database()
  return (await db.get('offline_cache', scopedKey(scope, key)))?.value ?? null
}

export async function enqueueOperation(scope, operation) {
  assertSafePayload(operation.payload)
  const now = new Date().toISOString()
  const db = await database()
  const transaction = db.transaction(['sync_queue', 'sync_metadata'], 'readwrite')
  const metadataKey = scopedKey(scope, 'metadata')
  const metadataRecord = await transaction.objectStore('sync_metadata').get(metadataKey)
  const metadata = metadataRecord?.value ?? {}
  const sequence = (metadata.queueSequence ?? 0) + 1
  const record = {
    id: operation.id ?? crypto.randomUUID(), scope, module: operation.module, entity: operation.entity,
    entityId: operation.entityId ?? null, action: operation.action, method: operation.method,
    path: operation.path, payload: operation.payload, lastKnownVersion: operation.lastKnownVersion ?? null,
    createdAt: now, sequence, retryCount: 0, lastAttemptAt: null, status: 'pending', failureCategory: null,
    failureMessage: null,
  }
  await transaction.objectStore('sync_queue').add(record)
  await transaction.objectStore('sync_metadata').put({ key: metadataKey, scope, value: { ...metadata, queueSequence: sequence } })
  await transaction.done
  return record
}

export async function queuedOperations(scope, statuses = ['pending', 'syncing', 'failed']) {
  const db = await database()
  const records = await db.getAllFromIndex('sync_queue', 'scope', scope)
  return records.filter((record) => statuses.includes(record.status)).sort((left, right) => (left.sequence ?? 0) - (right.sequence ?? 0) || left.createdAt.localeCompare(right.createdAt) || left.id.localeCompare(right.id))
}

export async function updateOperation(id, changes) {
  const db = await database()
  const record = await db.get('sync_queue', id)
  if (!record) return null
  const updated = { ...record, ...changes }
  await db.put('sync_queue', updated)
  return updated
}

export async function discardOperation(id) {
  const db = await database()
  await db.delete('sync_queue', id)
}

export async function syncMetadata(scope) {
  const db = await database()
  return (await db.get('sync_metadata', scopedKey(scope, 'metadata')))?.value ?? {}
}

export async function updateSyncMetadata(scope, changes) {
  const db = await database()
  const key = scopedKey(scope, 'metadata')
  const current = (await db.get('sync_metadata', key))?.value ?? {}
  const value = { ...current, ...changes }
  await db.put('sync_metadata', { key, scope, value })
  return value
}

export async function clearOfflineScope(scope) {
  if (!scope) return
  const db = await database()
  const transaction = db.transaction(['offline_cache', 'sync_queue', 'sync_metadata'], 'readwrite')
  for (const name of ['offline_cache', 'sync_queue', 'sync_metadata']) {
    const store = transaction.objectStore(name)
    const records = await store.index('scope').getAll(scope)
    for (const record of records) await store.delete(record.key ?? record.id)
  }
  await transaction.done
}

export function classifySyncFailure(error) {
  if (error?.code === 'network_error' || (typeof navigator !== 'undefined' && navigator.onLine === false)) return 'network'
  if (error?.code === 'session_expired' || error?.status === 401) return 'authentication'
  if (error?.status === 403) return 'forbidden'
  if (error?.status === 409) return 'conflict'
  if (error?.status === 400 || error?.status === 422) return 'validation'
  return 'server'
}
