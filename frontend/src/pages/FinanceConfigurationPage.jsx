import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiClient } from '../api/client'
import SchoolFinancialNavigation from '../components/SchoolFinancialNavigation'

export default function FinanceConfigurationPage() {
  const [data, setData] = useState({ accounts: [], categories: [] }), [revision, setRevision] = useState(0), [error, setError] = useState('')
  useEffect(() => { apiClient('/school/finance/lookups/').then(setData).catch(() => setError('Finance configuration could not be loaded.')) }, [revision])
  async function deactivate(kind, item) { try { await apiClient(`/school/finance/${kind}/${item.id}/`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ is_active: !item.is_active }) }); setRevision(old => old + 1) } catch { setError('Configuration could not be updated.') } }
  return <main className="student-page"><Link to="/school/finance">Back to Finance</Link><h1>Accounts and Categories</h1><SchoolFinancialNavigation /><p>Cash and bank accounts classify recorded transactions. Balances are based on recorded history. Bank Reconciliation is FUTURE.</p>{error && <p role="alert">{error}</p>}{['accounts', 'categories'].map(kind => <section className="profile-section" key={kind}><h2>{kind === 'accounts' ? 'Cash / Bank Accounts' : 'Income / Expense Categories'}</h2><ConfigurationForm kind={kind} onSaved={() => setRevision(old => old + 1)} />{data[kind].map(item => <p key={item.id}>{item.name} · {item.kind} · {item.is_active ? 'Active' : 'Inactive'} <button onClick={() => deactivate(kind, item)}>{item.is_active ? 'Deactivate' : 'Activate'} {item.name}</button></p>)}</section>)}</main>
}

function ConfigurationForm({ kind, onSaved }) {
  const [name, setName] = useState(''), [type, setType] = useState(kind === 'accounts' ? 'cash' : 'income'), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  async function save(event) { event.preventDefault(); setBusy(true); setError(''); try { await apiClient(`/school/finance/${kind}/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, kind: type, is_active: true }) }); setName(''); onSaved() } catch (failure) { setError(Object.values(failure.data || {}).flat().join(' ') || 'Could not save configuration.') } finally { setBusy(false) } }
  return <form className="student-form" onSubmit={save}><label>{kind === 'accounts' ? 'Account Name' : 'Category Name'}<input maxLength="100" required value={name} onChange={e => setName(e.target.value)} /></label><label>{kind === 'accounts' ? 'Account Type' : 'Category Type'}<select value={type} onChange={e => setType(e.target.value)}>{(kind === 'accounts' ? ['cash', 'bank', 'other'] : ['income', 'expense']).map(value => <option key={value} value={value}>{value}</option>)}</select></label>{error && <p role="alert">{error}</p>}<button disabled={busy}>Add {kind === 'accounts' ? 'Account' : 'Category'}</button></form>
}
