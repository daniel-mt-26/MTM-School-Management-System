import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { getSchoolClasses, getStudents } from '../api/students'

function StudentsPage() {
  const [students, setStudents] = useState([])
  const [classes, setClasses] = useState([])
  const [filters, setFilters] = useState({ q: '', school_class: '', is_active: '' })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    getSchoolClasses().then(setClasses).catch(() => setError('We could not load school classes.'))
  }, [])

  useEffect(() => {
    let active = true
    const timeout = setTimeout(() => {
      setLoading(true)
      setError('')
      getStudents({ ...filters, q: filters.q.trim() })
        .then((data) => { if (active) setStudents(data) })
        .catch(() => { if (active) setError('We could not load students. Please try again.') })
        .finally(() => { if (active) setLoading(false) })
    }, filters.q ? 250 : 0)
    return () => { active = false; clearTimeout(timeout) }
  }, [filters])

  function changeFilter(event) {
    setFilters((current) => ({ ...current, [event.target.name]: event.target.value }))
  }

  return (
    <main className="student-page">
      <header className="student-page-header">
        <div><Link to="/school" className="dashboard-link">← Back to School Dashboard</Link><h1>Students</h1></div>
        <Link to="/school/students/new" className="primary-link">Add Student</Link>
      </header>

      <section className="student-filters" aria-label="Student filters">
        <input name="q" type="search" value={filters.q} onChange={changeFilter} placeholder="Search name or admission number" aria-label="Search students" />
        <select name="school_class" value={filters.school_class} onChange={changeFilter} aria-label="Filter by class">
          <option value="">All classes</option>
          {classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
        <select name="is_active" value={filters.is_active} onChange={changeFilter} aria-label="Filter by status">
          <option value="">All statuses</option><option value="true">Active</option><option value="false">Inactive</option>
        </select>
      </section>

      {error && <p className="form-error" role="alert">{error}</p>}
      {loading ? <p className="student-state">Loading students…</p> : (
        students.length === 0 ? <p className="student-state">No students match the current filters.</p> : (
          <div className="student-table-wrap">
            <table className="student-table">
              <thead><tr><th>Admission Number</th><th>Student Name</th><th>Class</th><th>Status</th><th>Actions</th></tr></thead>
              <tbody>{students.map((student) => (
                <tr key={student.id}>
                  <td>{student.admission_number}</td><td>{student.display_name}</td><td>{student.class_name}</td>
                  <td><span className={`status-badge ${student.is_active ? 'active' : 'inactive'}`}>{student.is_active ? 'Active' : 'Inactive'}</span></td>
                  <td><Link to={`/school/students/${student.id}`}>View</Link></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )
      )}
    </main>
  )
}

export default StudentsPage
