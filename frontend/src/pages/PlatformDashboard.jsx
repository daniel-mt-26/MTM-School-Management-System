import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { platformDashboard } from '../api/platform'
import AccountMenu from '../components/AccountMenu'

export default function PlatformDashboard() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    platformDashboard().then(setData).catch(() => setError('Platform information could not be loaded.'))
  }, [])
  const cards = data ? [
    ['Total Schools', data.total_schools], ['Active Schools', data.active_schools],
    ['Suspended Schools', data.suspended_schools], ['Archived Schools', data.archived_schools],
    ['School Administrators', data.total_school_administrators], ['Total Students', data.total_students],
  ] : []
  return (
    <main className="student-page">
      <header className="student-page-header">
        <div><h1>MTM Platform</h1><p>Operational overview across schools.</p></div>
        <AccountMenu />
      </header>
      <nav className="communication-nav">
        <Link className="primary-link" to="/platform/schools/new">Create school</Link>
        <Link to="/platform/schools">Schools</Link><Link to="/platform/audit">Platform audit</Link>
      </nav>
      {error ? <p className="form-error" role="alert">{error}</p> : !data ? <p>Loading platform dashboard…</p> : <>
        <section className="dashboard-navigation">{cards.map(([label, value]) => <div className="dashboard-card" key={label}><h2>{value}</h2><p>{label}</p></div>)}</section>
        <section className="profile-section"><h2>Recently created schools</h2>{data.recently_created_schools.map(school => <p key={school.id}><Link to={`/platform/schools/${school.id}`}>{school.name}</Link> · {school.status}</p>)}</section>
      </>}
    </main>
  )
}
