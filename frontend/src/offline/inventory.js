import {
  cacheValue, cachedValue, enqueueOperation, queuedOperations, syncMetadata, updateSyncMetadata,
} from './db.js'

const CACHE_KEY = 'inventory:state'
const LOCAL_PREFIX = 'local:'

const signedQuantity = (movement) => movement.direction === 'in' ? Number(movement.quantity) : -Number(movement.quantity)
const isLocalId = (id) => typeof id === 'string' && id.startsWith(LOCAL_PREFIX)

export function localId(operationId) {
  return `${LOCAL_PREFIX}${operationId}`
}

export function isLocalRecord(record) {
  return isLocalId(record?.id)
}

export async function cachedInventory(scope) {
  return cachedValue(scope, CACHE_KEY)
}

export async function cacheInventory(scope, state) {
  const cachedAt = new Date().toISOString()
  const value = { ...state, cachedAt }
  await cacheValue(scope, CACHE_KEY, value)
  await updateSyncMetadata(scope, { inventoryCachedAt: cachedAt })
  return value
}

function stockStatus(item, value) {
  if (value <= 0) return 'out_of_stock'
  if (value <= Number(item.minimum_stock_level ?? 0)) return 'low_stock'
  return 'in_stock'
}

function localMovement(operation, items, variants) {
  const item = items.find((entry) => String(entry.id) === String(operation.payload.item))
  const variant = variants.find((entry) => String(entry.id) === String(operation.payload.variant))
  return {
    id: localId(operation.id), item: operation.payload.item, variant: operation.payload.variant ?? null,
    item_name: item?.name ?? 'Inventory item', variant_name: variant?.name ?? null,
    movement_type: operation.payload.movement_type, direction: operation.payload.direction,
    quantity: Number(operation.payload.quantity), signed_quantity: signedQuantity(operation.payload),
    unit_cost: operation.payload.unit_cost ?? null, notes: operation.payload.notes ?? '',
    created_at: operation.createdAt, created_by_name: 'You', syncStatus: operation.status,
    syncOperationId: operation.id, failureCategory: operation.failureCategory,
    failureMessage: operation.failureMessage,
  }
}

export async function inventoryWithLocalChanges(scope, base) {
  if (!base) return null
  const pending = await queuedOperations(scope)
  const categories = [...(base.categories ?? [])]
  const items = [...(base.items ?? [])].map((item) => ({ ...item, variants: [...(item.variants ?? [])] }))
  const variants = [...(base.variants ?? [])]

  pending.filter((operation) => operation.module === 'inventory' && operation.action === 'create').forEach((operation) => {
    const id = localId(operation.id)
    if (operation.entity === 'category' && !categories.some((entry) => entry.id === id)) {
      categories.push({ id, ...operation.payload, is_active: true, syncStatus: operation.status, syncOperationId: operation.id })
    }
    if (operation.entity === 'item' && !items.some((entry) => entry.id === id)) {
      const category = categories.find((entry) => String(entry.id) === String(operation.payload.category))
      items.push({ id, ...operation.payload, category_name: category?.name ?? 'Pending category', variants: [], available_stock: 0, stock_status: 'out_of_stock', quantity_required_to_minimum: Number(operation.payload.minimum_stock_level ?? 0), is_active: true, syncStatus: operation.status, syncOperationId: operation.id })
    }
    if (operation.entity === 'variant' && !variants.some((entry) => entry.id === id)) {
      const item = items.find((entry) => String(entry.id) === String(operation.payload.item))
      const record = { id, ...operation.payload, item_name: item?.name ?? 'Pending item', available_stock: 0, is_active: true, syncStatus: operation.status, syncOperationId: operation.id }
      variants.push(record)
      if (item) item.variants.push(record)
    }
  })

  const unfinishedMovements = pending.filter((operation) => operation.module === 'inventory' && operation.entity === 'movement')
  const movements = [...unfinishedMovements.map((operation) => localMovement(operation, items, variants)), ...(base.movements ?? [])]
  const movementByItem = new Map()
  const movementByVariant = new Map()
  unfinishedMovements.forEach((operation) => {
    const change = signedQuantity(operation.payload)
    const itemId = String(operation.payload.item)
    movementByItem.set(itemId, (movementByItem.get(itemId) ?? 0) + change)
    if (operation.payload.variant) {
      const variantId = String(operation.payload.variant)
      movementByVariant.set(variantId, (movementByVariant.get(variantId) ?? 0) + change)
    }
  })
  const adjustedVariants = variants.map((variant) => ({ ...variant, available_stock: Number(variant.available_stock ?? 0) + (movementByVariant.get(String(variant.id)) ?? 0) }))
  const adjustedItems = items.map((item) => {
    const available = Number(item.available_stock ?? 0) + (movementByItem.get(String(item.id)) ?? 0)
    const itemVariants = adjustedVariants.filter((variant) => String(variant.item) === String(item.id))
    return { ...item, variants: itemVariants, available_stock: available, stock_status: stockStatus(item, available), quantity_required_to_minimum: Math.max(0, Number(item.minimum_stock_level ?? 0) - available) }
  })
  const activeItems = adjustedItems.filter((item) => item.is_active)
  const summary = {
    total_active_items: activeItems.length,
    low_stock_items: activeItems.filter((item) => item.stock_status === 'low_stock'),
    out_of_stock_items: activeItems.filter((item) => item.stock_status === 'out_of_stock'),
    recent_stock_movements: movements.slice(0, 10),
  }
  return { ...base, categories, items: adjustedItems, variants: adjustedVariants, movements, summary, hasLocalChanges: pending.some((operation) => operation.module === 'inventory') }
}

export async function queueInventoryCreate(scope, entity, payload) {
  const id = crypto.randomUUID()
  const operation = await enqueueOperation(scope, {
    id, module: 'inventory', entity, entityId: localId(id), action: 'create', method: 'POST',
    path: `/school/inventory/${entity === 'category' ? 'categories' : `${entity}s`}/`, payload,
  })
  return { ...operation, localId: localId(id) }
}

export async function queueInventoryMovement(scope, payload) {
  const id = crypto.randomUUID()
  return enqueueOperation(scope, {
    id, module: 'inventory', entity: 'movement', entityId: localId(id), action: 'create', method: 'POST',
    path: '/school/inventory/movements/', payload,
  })
}

export async function localIdMappings(scope) {
  return (await syncMetadata(scope)).inventoryIdMappings ?? {}
}

export async function mapLocalId(scope, id, serverId) {
  const mappings = await localIdMappings(scope)
  const value = { ...mappings, [id]: serverId }
  await updateSyncMetadata(scope, { inventoryIdMappings: value })
  return value
}

export function replaceMappedIds(value, mappings) {
  if (Array.isArray(value)) return value.map((entry) => replaceMappedIds(entry, mappings))
  if (!value || typeof value !== 'object') return mappings[value] ?? value
  return Object.fromEntries(Object.entries(value).map(([key, entry]) => [key, replaceMappedIds(entry, mappings)]))
}

export async function resolveInventoryOperation(scope, operation, response) {
  if (!['inventory', 'homework'].includes(operation.module)) return
  if (operation.action === 'create' && operation.entity !== 'movement' && response?.id != null) {
    await mapLocalId(scope, localId(operation.id), response.id)
  }
}

export function syncIssueMessage(error) {
  const data = error?.data
  if (typeof data?.detail === 'string') return data.detail
  if (data && typeof data === 'object') return Object.values(data).flat().filter((value) => typeof value === 'string').join(' ') || 'The server rejected this change.'
  if (error?.code === 'session_expired') return 'Sign in again with this account before retrying.'
  return 'The change could not be synchronized.'
}
