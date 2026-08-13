import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getParents } from '../api/parents'

export default function ParentsPage() {
  const [parents, setParents] = useState([])
  const [q, setQ] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    const timer = setTimeout(() => getParents(q.trim()).then(setParents).catch(() => setError('We could not load parents.')), 250)
    return () => clearTimeout(timer)
  }, [q])

  return <main className="student-page">
    <header className="student-page-header"><div><Link to="/school" className="dashboard-link">Back to School Dashboard</Link><h1>Parents & Guardians</h1></div><Link to="/school/parents/new" className="primary-link">Add Parent / Guardian</Link></header>
    <input className="parent-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, username, email or phone" />
    {error && <p className="form-error">{error}</p>}
    <div className="student-table-wrap"><table className="student-table"><thead><tr><th>Name</th><th>Username</th><th>Phone</th><th>Email</th><th>Children</th><th>Actions</th></tr></thead><tbody>
      {parents.length ? parents.map((parent) => <tr key={parent.id}><td>{parent.display_name}</td><td>{parent.username}</td><td>{parent.phone}</td><td>{parent.email || '—'}</td><td>{parent.child_count}</td><td><Link to={`/school/parents/${parent.id}`}>View</Link><span> · </span><Link to={`/school/parents/${parent.id}/edit`}>Edit</Link></td></tr>) : <tr><td colSpan="6" className="empty-cell">No parents or guardians match this search.</td></tr>}
    </tbody></table></div>
  </main>
}
