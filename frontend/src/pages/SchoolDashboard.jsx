import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { getSchoolProfile, searchSchool } from '../api/school'

const EMPTY_RESULTS = { students: [], parents: [], classes: [] }

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
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(EMPTY_RESULTS)
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState('')

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

  useEffect(() => {
    const trimmedQuery = query.trim()
    if (trimmedQuery.length < 2) return undefined

    let active = true
    const timeout = setTimeout(() => {
      setSearching(true)
      setSearchError('')
      searchSchool(trimmedQuery)
        .then((searchResults) => {
          if (active) setResults(searchResults)
        })
        .catch(() => {
          if (active) setSearchError('Search is unavailable right now. Please try again.')
        })
        .finally(() => {
          if (active) setSearching(false)
        })
    }, 300)

    return () => {
      active = false
      clearTimeout(timeout)
    }
  }, [query])

  function changeQuery(event) {
    const value = event.target.value
    setQuery(value)
    if (value.trim().length < 2) {
      setResults(EMPTY_RESULTS)
      setSearchError('')
      setSearching(false)
    }
  }

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
            value={query}
            onChange={changeQuery}
          />
          {query.trim().length >= 2 && (
            <div className="search-results" aria-live="polite">
              {searching && <p className="search-status">Searching…</p>}
              {searchError && <p className="search-error" role="alert">{searchError}</p>}
              {!searching && !searchError && (
                <>
                  {results.students.length > 0 && (
                    <SearchGroup title="Students" items={results.students} path="/school/students" renderItem={(item) => (
                      <><strong>{item.display_name}</strong><span>{item.admission_number} · {item.class_name}</span></>
                    )} />
                  )}
                  {results.parents.length > 0 && (
                    <SearchGroup title="Parents" items={results.parents} path="/school/parents" renderItem={(item) => (
                      <><strong>{item.display_name}</strong><span>{item.phone}</span></>
                    )} />
                  )}
                  {results.classes.length > 0 && (
                    <SearchGroup title="Classes" items={results.classes} path="/school/academics" renderItem={(item) => <strong>{item.name}</strong>} />
                  )}
                  {results.students.length === 0 && results.parents.length === 0 && results.classes.length === 0 && (
                    <p className="search-status">No matching students, parents, or classes.</p>
                  )}
                </>
              )}
            </div>
          )}
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

function SearchGroup({ title, items, path, renderItem }) {
  return (
    <section className="search-group">
      <h2>{title}</h2>
      {items.map((item) => <Link key={item.id} to={path}>{renderItem(item)}</Link>)}
    </section>
  )
}

export default SchoolDashboard;
