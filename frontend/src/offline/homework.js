import { cacheValue, cachedValue, enqueueOperation, queuedOperations } from './db.js'
import { localId } from './inventory.js'

const CACHE_KEY = 'homework:state'

export async function cacheHomework(scope, state) {
  const value = { ...state, cachedAt: new Date().toISOString() }
  await cacheValue(scope, CACHE_KEY, value)
  return value
}

export const cachedHomework = (scope) => cachedValue(scope, CACHE_KEY)

export async function queueHomework(scope, payload) {
  const id = crypto.randomUUID()
  return enqueueOperation(scope, { id, module: 'homework', entity: 'homework', entityId: localId(id), action: 'create', method: 'POST', path: '/school/homework/', payload })
}

export async function homeworkWithLocalChanges(scope, base) {
  if (!base) return null
  const operations = await queuedOperations(scope)
  const local = operations.filter((operation) => operation.module === 'homework' && operation.entity === 'homework').map((operation) => ({
    id: localId(operation.id), ...operation.payload, class_name: base.classes.find((item) => String(item.id) === String(operation.payload.school_class))?.name ?? 'Pending class',
    subject_name: operation.payload.subject ? base.subjects.find((item) => String(item.id) === String(operation.payload.subject))?.name ?? 'Pending subject' : null,
    attachments: [], created_by_name: 'You', syncStatus: operation.status, syncOperationId: operation.id,
  }))
  return { ...base, items: [...local, ...base.items], hasLocalChanges: local.length > 0 }
}
