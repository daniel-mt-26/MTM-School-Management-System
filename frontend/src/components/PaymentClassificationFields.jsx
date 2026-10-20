import { useEffect, useState } from 'react'
import { apiClient } from '../api/client'

export default function PaymentClassificationFields({ account, category, onChange }) {
  const [lookups, setLookups] = useState(null)
  useEffect(() => { apiClient('/school/finance/lookups/').then(setLookups).catch(() => setLookups({ accounts: [], categories: [] })) }, [])
  return <div className="form-columns"><label>Cash / Bank Account<select value={account || ''} onChange={e => onChange('account', e.target.value ? Number(e.target.value) : null)}><option value="">Unassigned / unspecified</option>{(lookups?.accounts || []).filter(x => x.is_active).map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label><label>Income Category<select value={category || ''} onChange={e => onChange('income_category', e.target.value ? Number(e.target.value) : null)}><option value="">School Fee Payments</option>{(lookups?.categories || []).filter(x => x.kind === 'income' && x.is_active).map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label></div>
}
