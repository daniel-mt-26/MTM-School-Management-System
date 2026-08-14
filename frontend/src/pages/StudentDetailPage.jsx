import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { getAvailableParents, getStudent, linkParent, unlinkParent } from '../api/students'

function StudentDetailPage() {
  const { studentId } = useParams()
  const [student, setStudent] = useState(null)
  const [availableParents, setAvailableParents] = useState([])
  const [linkForm, setLinkForm] = useState({ parent: '', relationship: 'Guardian', is_primary_contact: false })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [linkError, setLinkError] = useState('')
  const [savingLink, setSavingLink] = useState(false)

  const loadStudent = useCallback(() => {
    return getStudent(studentId).then(setStudent)
  }, [studentId])

  useEffect(() => {
    Promise.all([loadStudent(), getAvailableParents().then(setAvailableParents)])
      .catch((requestError) => setError(requestError.status === 404 ? 'Student not found.' : 'We could not load the student profile.'))
      .finally(() => setLoading(false))
  }, [loadStudent])

  const selectableParents = useMemo(() => {
    const linked = new Set(student?.parents.map((link) => link.parent) || [])
    return availableParents.filter((parent) => !linked.has(parent.id))
  }, [availableParents, student])

  function changeLink(event) {
    const { name, type, checked, value } = event.target
    setLinkForm((current) => ({ ...current, [name]: type === 'checkbox' ? checked : value }))
  }

  async function submitLink(event) {
    event.preventDefault()
    setLinkError('')
    setSavingLink(true)
    try {
      await linkParent({ ...linkForm, student: Number(studentId), parent: Number(linkForm.parent) })
      await loadStudent()
      setLinkForm({ parent: '', relationship: 'Guardian', is_primary_contact: false })
    } catch (requestError) {
      const errors = requestError.data && Object.values(requestError.data).flat()
      setLinkError(errors?.[0] || 'We could not link this parent or guardian.')
    } finally {
      setSavingLink(false)
    }
  }

  async function removeLink(linkId) {
    setLinkError('')
    try {
      await unlinkParent(linkId)
      await loadStudent()
    } catch {
      setLinkError('We could not remove this parent or guardian link.')
    }
  }

  if (loading) return <main className="school-profile-state">Loading student profile…</main>
  if (error || !student) return <main className="school-profile-state" role="alert"><p>{error || 'Student not found.'}</p><Link to="/school/students" className="dashboard-link">Back to Students</Link></main>

  return (
    <main className="student-page">
      <header className="student-page-header">
        <div><Link to="/school/students" className="dashboard-link">← Back to Students</Link><h1>{student.display_name}</h1><p>{student.admission_number}</p></div>
        <Link to={`/school/students/${student.id}/edit`} className="primary-link">Edit Student</Link>
      </header>

      <section className="profile-section"><h2>Student Details</h2><dl className="detail-grid">
        <div><dt>Current Class</dt><dd>{student.class_name}<br /><Link to="/school/academics/timetables" className="dashboard-link">View Class Timetable</Link></dd></div><div><dt>Status</dt><dd>{student.is_active ? 'Active' : 'Inactive'}</dd></div>
        <div><dt>Date of Birth</dt><dd>{student.date_of_birth}</dd></div><div><dt>Initial Enrollment</dt><dd>{student.enrolled_on}</dd></div>
      </dl></section>

      <section className="profile-section"><h2>Enrollment History</h2>
        {student.enrollment_history.length === 0 ? <p className="muted-copy">No enrollment history has been recorded.</p> : <div className="history-list">{student.enrollment_history.map((item) => (
          <div key={item.id}><strong>{item.academic_year} · {item.class_name}</strong><span>{item.enrolled_on} — {item.left_on || 'Current'}</span></div>
        ))}</div>}
      </section>

      <section className="profile-section"><h2>Finance</h2><Link to={`/school/finance/students/${student.id}`} className="primary-link">View Finance</Link></section>

      <section className="profile-section"><h2>Parents or Guardians</h2>
        {student.parents.length === 0 ? <p className="muted-copy">No parents or guardians are linked.</p> : <div className="parent-link-list">{student.parents.map((link) => (
          <div key={link.id}><div><strong>{link.parent_name}</strong><span>{link.relationship}{link.is_primary_contact ? ' · Primary contact' : ''} · {link.phone}</span></div><button type="button" className="text-button" onClick={() => removeLink(link.id)}>Remove</button></div>
        ))}</div>}
        {selectableParents.length > 0 ? <form className="parent-link-form" onSubmit={submitLink}>
          <select name="parent" value={linkForm.parent} onChange={changeLink} required aria-label="Existing parent or guardian"><option value="">Select an existing parent</option>{selectableParents.map((parent) => <option key={parent.id} value={parent.id}>{parent.display_name} · {parent.phone}</option>)}</select>
          <input name="relationship" value={linkForm.relationship} onChange={changeLink} placeholder="Relationship" required aria-label="Relationship" />
          <label className="checkbox-label"><input name="is_primary_contact" type="checkbox" checked={linkForm.is_primary_contact} onChange={changeLink} /> Primary contact</label>
          <button type="submit" disabled={savingLink}>{savingLink ? 'Linking…' : 'Link Parent'}</button>
        </form> : <p className="muted-copy">No additional tenant-owned parents are available to link. Parent creation will be added in Phase 5.4.</p>}
        {linkError && <p className="form-error" role="alert">{linkError}</p>}
      </section>
    </main>
  )
}

export default StudentDetailPage
