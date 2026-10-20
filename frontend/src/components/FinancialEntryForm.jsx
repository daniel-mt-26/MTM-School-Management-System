import { useState } from 'react'
import { apiClient } from '../api/client'

const today = () => { const date = new Date(); return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}` }

export default function FinancialEntryForm({ expense = false, initial = null, lookups, onSaved, onCancel }) {
  const [form, setForm] = useState(() => ({ date: initial?.expense_date || today(), description: initial?.description || '', amount: initial?.amount || '',
    reference: initial?.reference || '', payment_method: initial?.payment_method || 'cash', account: initial?.account || '', notes: initial?.notes || '',
    source: '', payee: initial?.payee || '', category: initial?.finance_category ? `configured:${initial.finance_category}` : initial?.category || (expense ? 'other' : '') }))
  const [operation, setOperation] = useState(() => crypto.randomUUID())
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  const set = (key, value) => setForm(old => ({ ...old, [key]: value }))
  async function save(event) {
    event.preventDefault(); if (busy) return; setBusy(true); setError('')
    const configured = form.category.startsWith('configured:') ? Number(form.category.split(':')[1]) : null
    const payload = { description: form.description, amount: form.amount, reference: form.reference, payment_method: form.payment_method,
      account: form.account ? Number(form.account) : null, notes: form.notes,
      ...(expense ? { expense_date: form.date, category: configured ? 'other' : form.category, finance_category: configured, payee: form.payee } : { income_date: form.date, source: form.source, category: form.category ? Number(form.category) : null }) }
    try {
      const result = await apiClient(expense ? `/school/expenses/${initial ? `${initial.id}/` : ''}` : '/school/finance/other-income/', {
        method: initial ? 'PATCH' : 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': operation }, body: JSON.stringify(payload),
      })
      setOperation(crypto.randomUUID()); onSaved(result)
    } catch (failure) { setError(Object.values(failure.data || {}).flat().join(' ') || 'The record could not be saved. Retrying this entry uses the same operation to prevent duplicates.') }
    finally { setBusy(false) }
  }
  return <form className="student-form" onSubmit={save}><h2>{expense ? initial ? 'Edit Expense' : 'Record Expense' : 'Record Other Income'}</h2>{!expense && <p>For actual non-student receipts only. Record learner money in Payments; it already appears in Income and the Cash Book.</p>}
    <div className="form-columns"><label>Date<input type="date" required value={form.date} onChange={e => set('date', e.target.value)} /></label><label>Amount ({lookups.currency})<input type="number" min="0.01" step="0.01" required value={form.amount} onChange={e => set('amount', e.target.value)} /></label></div>
    {expense ? <label>Supplier / Payee<input maxLength="150" value={form.payee} onChange={e => set('payee', e.target.value)} /></label> : <label>Source<input maxLength="150" required value={form.source} onChange={e => set('source', e.target.value)} /></label>}
    <label>Description<input maxLength="255" required value={form.description} onChange={e => set('description', e.target.value)} /></label><label>Category<select value={form.category} onChange={e => set('category', e.target.value)}>{!expense && <option value="">Other Income</option>}{expense && lookups.expense_categories.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}{lookups.categories.filter(x => x.kind === (expense ? 'expense' : 'income') && (x.is_active || `configured:${x.id}` === form.category)).map(x => <option key={`configured:${x.id}`} value={expense ? `configured:${x.id}` : x.id}>{x.name}</option>)}</select></label>
    <div className="form-columns"><label>Payment Method<input maxLength="30" required list="finance-method-options" value={form.payment_method} onChange={e => set('payment_method', e.target.value)} /></label><label>Cash / Bank Account<select value={form.account} onChange={e => set('account', e.target.value)}><option value="">Unassigned / unspecified</option>{lookups.accounts.filter(x => x.is_active || String(x.id) === String(form.account)).map(x => <option key={x.id} value={x.id}>{x.name} ({x.kind})</option>)}</select></label></div>
    <datalist id="finance-method-options">{lookups.payment_methods.map(method => <option key={method} value={method} />)}</datalist><label>Reference<input maxLength="100" value={form.reference} onChange={e => set('reference', e.target.value)} /></label><label>Supporting Information<textarea rows="3" value={form.notes} onChange={e => set('notes', e.target.value)} /></label>
    {error && <p role="alert">{error}</p>}<button disabled={busy}>{busy ? 'Saving…' : initial ? 'Save Changes' : expense ? 'Save Expense' : 'Save Other Income'}</button>{initial && <button type="button" onClick={onCancel}>Cancel Edit</button>}
  </form>
}
