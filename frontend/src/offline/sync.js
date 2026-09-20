import {
  classifySyncFailure, queuedOperations, syncMetadata, updateOperation, updateSyncMetadata,
} from './db.js'
import { localIdMappings, replaceMappedIds, resolveInventoryOperation, syncIssueMessage } from './inventory.js'

const MAX_RETRIES = 5
const RETRY_BASE_MS = 30_000

function retryAllowed(operation, now, force) {
  const temporary = ['network', 'server']
  if (operation.status === 'failed' && !force && !temporary.includes(operation.failureCategory)) return false
  if (force || !operation.lastAttemptAt) return true
  const delay = RETRY_BASE_MS * (2 ** Math.min(operation.retryCount, 4))
  return now - new Date(operation.lastAttemptAt).getTime() >= delay
}

function unresolvedLocalReference(value, mappings) {
  if (Array.isArray(value)) return value.some((entry) => unresolvedLocalReference(entry, mappings))
  if (!value || typeof value !== 'object') return typeof value === 'string' && value.startsWith('local:') && mappings[value] == null
  return Object.values(value).some((entry) => unresolvedLocalReference(entry, mappings))
}

export async function sendQueuedOperation(operation) {
  const { apiClient } = await import('../api/client.js')
  return apiClient(operation.path, {
    method: operation.method,
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': operation.id },
    body: JSON.stringify(operation.payload),
  })
}

export async function processSyncQueue(scope, { send = sendQueuedOperation, force = false, onChange = () => {} } = {}) {
  const now = Date.now()
  const operations = (await queuedOperations(scope, ['pending', 'failed']))
    .filter((operation) => operation.retryCount < MAX_RETRIES && retryAllowed(operation, now, force))
  let completed = 0
  for (const operation of operations) {
    const mappings = await localIdMappings(scope)
    if (unresolvedLocalReference(operation.payload, mappings)) break
    await updateOperation(operation.id, { status: 'syncing', lastAttemptAt: new Date().toISOString(), failureCategory: null })
    onChange()
    try {
      const resolvedOperation = { ...operation, payload: replaceMappedIds(operation.payload, mappings) }
      const response = await send(resolvedOperation)
      await resolveInventoryOperation(scope, operation, response)
      await updateOperation(operation.id, { status: 'completed', completedAt: new Date().toISOString(), failureCategory: null })
      completed += 1
    } catch (error) {
      await updateOperation(operation.id, {
        status: 'failed', retryCount: operation.retryCount + 1, lastAttemptAt: new Date().toISOString(),
        failureCategory: classifySyncFailure(error), failureMessage: syncIssueMessage(error),
      })
      break
    }
    onChange()
  }
  if (completed) await updateSyncMetadata(scope, { lastSyncedAt: new Date().toISOString() })
  return { completed, metadata: await syncMetadata(scope) }
}
