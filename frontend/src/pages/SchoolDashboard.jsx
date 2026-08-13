import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { getSchoolProfile } from '../api/school'

function getInitials(name) {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0])
    .join('')
    .toUpperCase() || 'S'
}

function SchoolDashboard() {
  const [school, setSchool] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true

    getSchoolProfile()
      .then((profile) => {
        if (active) setSchool(profile)
      })
      .catch(() => {
        if (active) setError('We could not load your school profile. Please try again.')
      })

    return () => {
      active = false
    }
  }, [])

  if (error) {
    return (
      <main className="school-profile-state" role="alert">
        <p>{error}</p>
        <button type="button" onClick={() => window.location.reload()}>Try again</button>
      </main>
    )
  }

  if (!school) {
    return <main className="school-profile-state" aria-live="polite">Loading school profile…</main>
  }

  return (
    <div className="school-dashboard">
      <header className="school-header">
        <div className="school-identity">
          {school.logo ? (
            <img className="school-logo" src={school.logo} alt={`${school.name} logo`} />
          ) : (
            <div className="school-logo" aria-hidden="true">{getInitials(school.name)}</div>
          )}

          <div>
            <h1>{school.name}</h1>
            <p>School Management System</p>
          </div>
        </div>

      </header>

      <main className="dashboard-content">
        <section className="dashboard-search">
          <input
            type="search"
            placeholder="Search students, parents, records..."
            aria-label="Search students, parents and records"
          />
        </section>

        <section className="dashboard-navigation">
          <Link to="/school/students" className="dashboard-card">
            <h2>Students</h2>
            <p>Manage student records and information.</p>
          </Link>

          <Link to="/school/parents" className="dashboard-card">
            <h2>Parents</h2>
            <p>Manage parent information and linked students.</p>
          </Link>

          <Link to="/school/academics" className="dashboard-card">
            <h2>Academics</h2>
            <p>Classes, subjects, enrolments and results.</p>
          </Link>

          <Link to="/school/finance" className="dashboard-card">
            <h2>Finance</h2>
            <p>Fees, payments, receipts and ledgers.</p>
          </Link>

          <Link to="/school/communication" className="dashboard-card">
            <h2>Communication</h2>
            <p>Notifications and school communication.</p>
          </Link>

          <Link to="/school/settings" className="dashboard-card">
            <h2>Settings</h2>
            <p>Configure your school's information and preferences.</p>
          </Link>
        </section>
      </main>
    </div>
  );
}

export default SchoolDashboard;
