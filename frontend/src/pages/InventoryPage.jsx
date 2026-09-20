import { useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { getInventoryCategories, getInventoryItems, getInventoryMovements, getInventorySummary, getInventoryVariants, saveInventoryRecord } from '../api/inventory'
import { OfflineContext } from '../offline/context'
import { discardOperation, updateOperation } from '../offline/db'
import { cacheInventory, cachedInventory, inventoryWithLocalChanges, isLocalRecord, queueInventoryCreate, queueInventoryMovement } from '../offline/inventory'

const sections = [['overview', 'Overview'], ['items', 'Items'], ['categories', 'Categories'], ['movements', 'Stock Movements']]
const emptyItem = { category: '', name: '', code: '', description: '', unit: 'each', minimum_stock_level: '0', cost_per_unit: '', storage_location: '', variants: '' }
const emptyCategory = { name: '', description: '' }
const emptyMovement = { item: '', variant: '', movement_type: 'restock', direction: 'in', quantity: '', unit_cost: '', notes: '' }
const noRecords = []
const apiMessage = (error, fallback) => error?.data && typeof error.data === 'object' ? Object.values(error.data).flat().join(' ') : fallback
const snapshot = ([categories, items, variants, movements, summary]) => ({ categories, items, variants, movements, summary })

export default function InventoryPage() {
  const { section = 'overview' } = useParams()
  return <InventoryContent key={section} section={sections.some(([path]) => path === section) ? section : 'overview'} />
}

function InventoryContent({ section }) {
  const offline = useContext(OfflineContext)
  const { scope, isReachable, queue = [], refresh, syncNow, syncRevision } = offline ?? {}
  const [inventory, setInventory] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [itemForm, setItemForm] = useState(emptyItem)
  const [categoryForm, setCategoryForm] = useState(emptyCategory)
  const [movementForm, setMovementForm] = useState(emptyMovement)
  const [filters, setFilters] = useState({ q: '', category: '', status: '' })
  const [fromCache, setFromCache] = useState(false)

  const loadCached = useCallback(async () => {
    const display = await inventoryWithLocalChanges(scope, await cachedInventory(scope))
    setInventory(display); setFromCache(true)
    return display
  }, [scope])
  const load = useCallback(async () => {
    if (!scope) return
    setLoading(true); setError('')
    if (isReachable) {
      try {
        const state = await cacheInventory(scope, snapshot(await Promise.all([getInventoryCategories(), getInventoryItems(), getInventoryVariants(), getInventoryMovements(), getInventorySummary()])))
        setInventory(await inventoryWithLocalChanges(scope, state)); setFromCache(false); setLoading(false); return
      } catch { /* The probe may become stale before these requests run. */ }
    }
    const cached = await loadCached()
    if (!cached) setError('Inventory is unavailable until it has loaded successfully while online.')
    setLoading(false)
  }, [isReachable, loadCached, scope])
  useEffect(() => { const timer = window.setTimeout(() => { void load() }, 0); return () => window.clearTimeout(timer) }, [load, syncRevision])

  const categories = inventory?.categories ?? noRecords
  const items = inventory?.items ?? noRecords
  const variants = inventory?.variants ?? noRecords
  const movements = inventory?.movements ?? noRecords
  const summary = inventory?.summary
  const issues = queue.filter((operation) => operation.module === 'inventory' && operation.status === 'failed')
  const filteredItems = useMemo(() => items.filter((item) => {
    const query = filters.q.trim().toLowerCase()
    const matches = !query || [item.name, item.code, item.category_name, item.storage_location].some((value) => value?.toLowerCase().includes(query))
    return matches && (!filters.category || String(item.category) === filters.category) && (!filters.status || item.stock_status === filters.status)
  }), [items, filters])
  const selectedItem = items.find((item) => String(item.id) === movementForm.item)
  const matchingVariants = variants.filter((variant) => String(variant.item) === movementForm.item && variant.is_active)
  const setForm = (setter, field, value) => setter((current) => ({ ...current, [field]: value }))
  const openForm = () => { setNotice(''); setError(''); setShowForm(true) }
  async function localSaved(message) { await loadCached(); await refresh?.(); setShowForm(false); setNotice(message) }

  async function saveCategory(event) {
    event.preventDefault(); setError(''); setNotice('')
    try {
      if (!isReachable) { await queueInventoryCreate(scope, 'category', categoryForm); setCategoryForm(emptyCategory); await localSaved('Category saved locally. It will sync when you reconnect.'); return }
      await saveInventoryRecord('categories', categoryForm); setCategoryForm(emptyCategory); setShowForm(false); setNotice('Category added.'); await load()
    } catch (caught) { setError(apiMessage(caught, 'The category could not be saved.')) }
  }
  async function saveItem(event) {
    event.preventDefault(); setError(''); setNotice('')
    const { variants: inputVariants, cost_per_unit: cost, minimum_stock_level: minimum, ...data } = itemForm
    const payload = { ...data, minimum_stock_level: Number(minimum || 0), cost_per_unit: cost || null }
    const names = inputVariants.split(',').map((value) => value.trim()).filter(Boolean)
    try {
      if (!isReachable) {
        const item = await queueInventoryCreate(scope, 'item', payload)
        for (const name of names) await queueInventoryCreate(scope, 'variant', { item: item.localId, name })
        setItemForm(emptyItem); await localSaved('Item saved locally. It will sync when you reconnect.'); return
      }
      const item = await saveInventoryRecord('items', payload)
      await Promise.all(names.map((name) => saveInventoryRecord('variants', { item: item.id, name })))
      setItemForm(emptyItem); setShowForm(false); setNotice('Inventory item added.'); await load()
    } catch (caught) { setError(apiMessage(caught, 'The inventory item could not be saved.')) }
  }
  async function saveMovement(event) {
    event.preventDefault(); setError(''); setNotice('')
    const { unit_cost: cost, quantity, ...data } = movementForm
    const payload = { ...data, variant: data.variant || null, quantity: Number(quantity), unit_cost: cost || null }
    try {
      if (!isReachable) {
        const selectedVariant = variants.find((variant) => String(variant.id) === String(payload.variant))
        if (isLocalRecord(selectedItem) || isLocalRecord(selectedVariant)) { setError('Connect to the internet before recording stock for an item that has not been synchronized yet.'); return }
        await queueInventoryMovement(scope, payload); setMovementForm(emptyMovement); await localSaved('Stock movement saved locally. It will sync when you reconnect.'); return
      }
      await saveInventoryRecord('movements', payload); setMovementForm(emptyMovement); setShowForm(false); setNotice('Stock movement recorded.'); await load()
    } catch (caught) { setError(apiMessage(caught, 'The stock movement could not be recorded.')) }
  }
  async function retry(operation) { await updateOperation(operation.id, { status: 'pending', retryCount: 0, failureCategory: null, failureMessage: null }); await refresh?.(); if (isReachable) await syncNow(true) }
  async function discard(operation) { await discardOperation(operation.id); await refresh?.(); await loadCached(); setNotice('Local inventory change discarded.') }
  const selectType = (value) => { const directions = { restock: 'in', returned: 'in', issued: 'out', sold: 'out', damaged: 'out' }; setMovementForm((current) => ({ ...current, movement_type: value, direction: directions[value] || current.direction })) }
  const form = section === 'categories' ? <CategoryForm form={categoryForm} set={setForm.bind(null, setCategoryForm)} onSubmit={saveCategory} /> : section === 'movements' ? <MovementForm form={movementForm} set={setForm.bind(null, setMovementForm)} items={items} variants={matchingVariants} selectedItem={selectedItem} onType={selectType} onSubmit={saveMovement} /> : <ItemForm form={itemForm} set={setForm.bind(null, setItemForm)} categories={categories.filter((category) => category.is_active)} onSubmit={saveItem} />

  return <main className="student-page">
    <header className="student-page-header"><div><Link to="/school" className="dashboard-link">Back to School Dashboard</Link><h1>Inventory</h1><p>Track stock through recorded movements and keep supplies available.</p></div><button type="button" className="primary-link" onClick={openForm}>{section === 'categories' ? '+ Add Category' : section === 'movements' ? '+ Record Stock Movement' : '+ Add Item'}</button></header>
    <nav className="communication-nav" aria-label="Inventory sections">{sections.map(([path, label]) => <Link key={path} className={section === path ? 'active' : ''} to={path === 'overview' ? '/school/inventory' : `/school/inventory/${path}`}>{label}</Link>)}</nav>
    {fromCache && inventory && <p className="inventory-cache-notice" role="status">Offline or cached inventory — showing data from last sync: {new Date(inventory.cachedAt).toLocaleString()}. {inventory.hasLocalChanges && 'Provisional local changes are included.'}</p>}
    {error && <p className="form-error" role="alert">{error}</p>}{notice && <p className="communication-notice">{notice}</p>}
    {issues.length > 0 && <SyncIssues operations={issues} items={items} variants={variants} onRetry={retry} onDiscard={discard} />}
    {showForm && <section className="profile-section inventory-form"><div className="inventory-form-heading"><h2>{section === 'categories' ? 'Add category' : section === 'movements' ? 'Record stock movement' : 'Add inventory item'}</h2><button type="button" className="text-button" onClick={() => setShowForm(false)}>Cancel</button></div>{form}</section>}
    {loading ? <div className="student-state">Loading inventory…</div> : section === 'overview' ? <Overview summary={summary} /> : section === 'items' ? <ItemsTable items={filteredItems} filters={filters} setFilters={setFilters} categories={categories} /> : section === 'categories' ? <CategoriesTable categories={categories} /> : <MovementsTable movements={movements} />}
  </main>
}

function Overview({ summary }) { if (!summary) return null; return <><section className="finance-summary inventory-summary"><SummaryCard label="Total Items" value={summary.total_active_items} /><SummaryCard label="Low Stock" value={summary.low_stock_items.length} /><SummaryCard label="Out of Stock" value={summary.out_of_stock_items.length} /></section><section className="profile-section"><h2>Recent Stock Movements</h2><MovementsTable movements={summary.recent_stock_movements} compact /></section></> }
function SummaryCard({ label, value }) { return <div><span>{label}</span><strong>{value}</strong></div> }
function statusLabel(status) { return ({ in_stock: 'In Stock', low_stock: 'Low Stock', out_of_stock: 'Out of Stock' })[status] || status }
function Status({ status }) { return <span className={'status-badge inventory-' + status}>{statusLabel(status)}</span> }
function SyncTag({ record }) { if (!record.syncStatus) return null; return <span className={'inventory-sync-tag ' + record.syncStatus}>{record.syncStatus === 'failed' ? 'Sync issue' : record.syncStatus === 'syncing' ? 'Syncing' : 'Pending sync'}</span> }
function ItemsTable({ items, filters, setFilters, categories }) { return <><section className="student-filters inventory-filters"><input type="search" placeholder="Search items" value={filters.q} onChange={(event) => setFilters((current) => ({ ...current, q: event.target.value }))} /><select value={filters.category} onChange={(event) => setFilters((current) => ({ ...current, category: event.target.value }))}><option value="">All categories</option>{categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select><select value={filters.status} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}><option value="">All stock states</option><option value="in_stock">In Stock</option><option value="low_stock">Low Stock</option><option value="out_of_stock">Out of Stock</option></select></section><section className="student-table-wrap"><table className="student-table"><thead><tr><th>Item</th><th>Category</th><th>Variants</th><th>Available</th><th>Minimum</th><th>Status</th><th>Storage Location</th></tr></thead><tbody>{items.length ? items.map((item) => <tr key={item.id}><td><strong>{item.name}</strong><SyncTag record={item} />{item.code && <span className="table-subtext">{item.code}</span>}</td><td>{item.category_name}</td><td>{item.variants.length ? item.variants.map((variant) => variant.name + ' (' + variant.available_stock + ')').join(', ') : '—'}</td><td>{item.available_stock} {item.unit}{item.syncStatus || item.variants.some((variant) => variant.syncStatus) ? <span className="table-subtext">Provisional</span> : null}</td><td>{item.minimum_stock_level}</td><td><Status status={item.stock_status} /></td><td>{item.storage_location || '—'}</td></tr>) : <tr><td className="empty-cell" colSpan="7">No inventory items match these filters.</td></tr>}</tbody></table></section></> }
function CategoriesTable({ categories }) { return <section className="student-table-wrap"><table className="student-table"><thead><tr><th>Category</th><th>Description</th><th>Status</th></tr></thead><tbody>{categories.length ? categories.map((category) => <tr key={category.id}><td>{category.name}<SyncTag record={category} /></td><td>{category.description || '—'}</td><td><span className={'status-badge ' + (category.is_active ? 'active' : 'inactive')}>{category.is_active ? 'Active' : 'Inactive'}</span></td></tr>) : <tr><td className="empty-cell" colSpan="3">No categories yet.</td></tr>}</tbody></table></section> }
function MovementsTable({ movements, compact = false }) { return <section className={compact ? 'student-table-wrap inventory-compact-table' : 'student-table-wrap'}><table className="student-table"><thead><tr><th>Date</th><th>Item</th><th>Variant</th><th>Movement</th><th>Quantity</th><th>Recorded By</th></tr></thead><tbody>{movements?.length ? movements.map((movement) => <tr key={movement.id}><td>{new Date(movement.created_at).toLocaleString()}<SyncTag record={movement} /></td><td>{movement.item_name}</td><td>{movement.variant_name || '—'}</td><td>{movement.movement_type.replaceAll('_', ' ')}</td><td className={movement.signed_quantity >= 0 ? 'inventory-in' : 'inventory-out'}>{movement.signed_quantity >= 0 ? '+' : ''}{movement.signed_quantity}{movement.syncStatus && <span className="table-subtext">Provisional</span>}</td><td>{movement.created_by_name}</td></tr>) : <tr><td className="empty-cell" colSpan="6">No stock movements have been recorded yet.</td></tr>}</tbody></table></section> }
function SyncIssues({ operations, items, variants, onRetry, onDiscard }) { return <section className="inventory-sync-issues" aria-live="polite"><h2>Sync issues</h2>{operations.map((operation) => { const item = items.find((entry) => String(entry.id) === String(operation.payload.item)); const variant = variants.find((entry) => String(entry.id) === String(operation.payload.variant)); const label = operation.entity === 'movement' ? (item?.name ?? 'Inventory item') + (variant ? ' / ' + variant.name : '') + ' — ' + operation.payload.movement_type + ' ' + operation.payload.quantity : operation.payload.name; return <div key={operation.id}><strong>{label}</strong><p>{operation.failureMessage || 'This local change needs review before it can synchronize.'}</p><button type="button" className="inline-button" onClick={() => onRetry(operation)}>Retry</button><button type="button" className="text-button" onClick={() => onDiscard(operation)}>Discard local operation</button></div> })}</section> }
function CategoryForm({ form, set, onSubmit }) { return <form className="student-form inventory-inner-form" onSubmit={onSubmit}><label>Name<input required value={form.name} onChange={(event) => set('name', event.target.value)} /></label><label>Description <span className="field-help">Optional</span><textarea value={form.description} onChange={(event) => set('description', event.target.value)} /></label><button type="submit">Save Category</button></form> }
function ItemForm({ form, set, categories, onSubmit }) { return <form className="student-form inventory-inner-form" onSubmit={onSubmit}><div className="form-columns"><label>Category<select required value={form.category} onChange={(event) => set('category', event.target.value)}><option value="">Choose category</option>{categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label><label>Name<input required value={form.name} onChange={(event) => set('name', event.target.value)} /></label><label>Item / SKU Code <span className="field-help">Optional</span><input value={form.code} onChange={(event) => set('code', event.target.value)} /></label><label>Unit<input required value={form.unit} placeholder="each, box, kg" onChange={(event) => set('unit', event.target.value)} /></label><label>Minimum Stock<input min="0" required type="number" value={form.minimum_stock_level} onChange={(event) => set('minimum_stock_level', event.target.value)} /></label><label>Cost Per Unit <span className="field-help">Optional</span><input min="0" step="0.01" type="number" value={form.cost_per_unit} onChange={(event) => set('cost_per_unit', event.target.value)} /></label><label>Storage Location <span className="field-help">Optional</span><input value={form.storage_location} onChange={(event) => set('storage_location', event.target.value)} /></label><label>Variants <span className="field-help">Optional; separate labels with commas</span><input value={form.variants} placeholder="Size 24, Size 26" onChange={(event) => set('variants', event.target.value)} /></label></div><label>Description <span className="field-help">Optional</span><textarea value={form.description} onChange={(event) => set('description', event.target.value)} /></label><button type="submit">Save Item</button></form> }
function MovementForm({ form, set, items, variants, selectedItem, onType, onSubmit }) { const adjustment = form.movement_type === 'adjustment'; const serverItems = items.filter((item) => item.is_active && !isLocalRecord(item)); const variantRequired = variants.length > 0; return <form className="student-form inventory-inner-form" onSubmit={onSubmit}><div className="form-columns"><label>Item<select required value={form.item} onChange={(event) => { set('item', event.target.value); set('variant', '') }}><option value="">Choose item</option>{serverItems.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Variant {variantRequired ? <span className="field-help">Required for this item</span> : <span className="field-help">Optional</span>}<select required={variantRequired} value={form.variant} onChange={(event) => set('variant', event.target.value)} disabled={!selectedItem}><option value="">{variantRequired ? 'Choose variant' : 'No variant'}</option>{variants.map((variant) => <option key={variant.id} value={variant.id}>{variant.name}</option>)}</select></label><label>Movement Type<select value={form.movement_type} onChange={(event) => onType(event.target.value)}>{[['restock', 'Restock'], ['issued', 'Issued'], ['sold', 'Sold'], ['damaged', 'Damaged'], ['adjustment', 'Adjustment'], ['returned', 'Returned']].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Direction<select value={form.direction} disabled={!adjustment} onChange={(event) => set('direction', event.target.value)}><option value="in">Increase stock</option><option value="out">Decrease stock</option></select></label><label>Quantity<input required min="1" type="number" value={form.quantity} onChange={(event) => set('quantity', event.target.value)} /></label><label>Unit Cost <span className="field-help">Optional</span><input min="0" step="0.01" type="number" value={form.unit_cost} onChange={(event) => set('unit_cost', event.target.value)} /></label></div><label>Reason / Notes {adjustment && <span className="field-help">Required for adjustments</span>}<textarea required={adjustment} value={form.notes} onChange={(event) => set('notes', event.target.value)} /></label><button type="submit">Record Movement</button></form> }

