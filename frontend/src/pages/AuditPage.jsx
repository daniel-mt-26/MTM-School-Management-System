import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiClient } from '../api/client'

export default function AuditPage() {
  const [logs, setLogs] = useState([])
  const [error, setError] = useState('')
  useEffect(() => { apiClient('/school/audit/').then(setLogs).catch(() => setError('We could not load audit history.')) }, [])
  return <main className="student-page"><header className="student-page-header"><div><Link to="/school/settings" className="dashboard-link">← Back to School Settings</Link><h1>Audit History</h1><p>Administrative changes recorded for this school.</p></div></header>{error ? <p className="form-error">{error}</p> : <section className="profile-section">{logs.length ? <div className="student-table-wrap"><table className="student-table"><thead><tr><th>Date</th><th>Actor</th><th>Action</th><th>Record</th><th>Description</th></tr></thead><tbody>{logs.map((log) => <tr key={log.id}><td>{new Date(log.created_at).toLocaleString()}</td><td>{log.actor_name}</td><td>{log.action.replaceAll('_', ' ')}</td><td>{log.resource_type}</td><td>{log.description || '—'}</td></tr>)}</tbody></table></div> : <p className="muted-copy">No administrative actions have been recorded yet.</p>}</section>}</main>
}
