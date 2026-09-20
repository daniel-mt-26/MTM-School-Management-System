import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { platformSchools } from '../api/platform'
export default function PlatformSchoolsPage() {
  const [query, setQuery] = useState(''); const [schools, setSchools] = useState([]); const [error, setError] = useState('')
  useEffect(() => { platformSchools(query).then(setSchools).catch(() => setError('Schools could not be loaded.')) }, [query])
  return <main className="student-page"><header className="student-page-header"><div><Link to="/platform" className="dashboard-link">Back to platform</Link><h1>Schools</h1></div><Link className="primary-link" to="/platform/schools/new">Create school</Link></header><input className="parent-search" aria-label="Search schools" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search school, email, or phone"/>{error ? <p className="form-error">{error}</p> : <section className="profile-section">{schools.map(school => <p key={school.id}><Link to={`/platform/schools/${school.id}`}>{school.name}</Link> · <strong>{school.status}</strong> · {school.email}</p>)}{!schools.length && <p>No schools match this search.</p>}</section>}</main>
}
