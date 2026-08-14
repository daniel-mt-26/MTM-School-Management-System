import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import StudentPicker from '../components/StudentPicker'
import { getParent, linkParentChild, unlinkParentChild } from '../api/parents'

export default function ParentDetailPage() {
  const { parentId } = useParams()
  const [parent, setParent] = useState(null)
  const [form, setForm] = useState({ relationship: 'Guardian', is_primary_contact: false })
  const [selectedStudent, setSelectedStudent] = useState(null)
  const [pickerKey, setPickerKey] = useState(0)
  const [error, setError] = useState('')
  const [linkError, setLinkError] = useState('')
  const [saving, setSaving] = useState(false)
  const load = useCallback(() => getParent(parentId).then(setParent), [parentId])

  useEffect(() => { load().catch(() => setError('We could not load this parent profile.')) }, [load])

  function change(event) {
    const { name, type, checked, value } = event.target
    setForm((current) => ({ ...current, [name]: type === 'checkbox' ? checked : value }))
  }

  function chooseStudent(student) {
    setLinkError('')
    if (student && parent.children.some((child) => String(child.student) === String(student.id))) {
      setSelectedStudent(null)
      setLinkError('This student is already linked to this parent.')
      return
    }
    setSelectedStudent(student)
  }

  async function linkChild(event) {
    event.preventDefault()
    setLinkError('')
    if (!selectedStudent) {
      setLinkError('Search for and select a child before linking.')
      return
    }
    if (parent.children.some((child) => String(child.student) === String(selectedStudent.id))) {
      setSelectedStudent(null)
      setPickerKey((current) => current + 1)
      setLinkError('This student is already linked to this parent.')
      return
    }
    setSaving(true)
    try {
      await linkParentChild({ ...form, parent: Number(parentId), student: Number(selectedStudent.id) })
      await load()
      setForm({ relationship: 'Guardian', is_primary_contact: false })
      setSelectedStudent(null)
      setPickerKey((current) => current + 1)
    } catch (requestError) {
      setLinkError(Object.values(requestError.data || {}).flat().join(' ') || 'We could not link this child. The selected student may no longer be available.')
    } finally {
      setSaving(false)
    }
  }

  async function unlinkChild(id) {
    setLinkError('')
    try { await unlinkParentChild(id); await load() } catch { setLinkError('We could not unlink this child.') }
  }

  if (!parent && !error) return <main className="school-profile-state">Loading parent…</main>
  if (error || !parent) return <main className="school-profile-state" role="alert"><p>{error || 'Parent not found.'}</p><Link to="/school/parents" className="dashboard-link">Back to Parents</Link></main>

  const linkedStudentIds = parent.children.map((child) => child.student)
  return <main className="student-page"><header className="student-page-header"><div><Link to="/school/parents" className="dashboard-link">Back to Parents</Link><h1>{parent.first_name} {parent.last_name}</h1></div><Link to={`/school/parents/${parent.id}/edit`} className="primary-link">Edit Parent</Link></header>
    <section className="profile-section"><h2>Parent Details</h2><dl className="detail-grid"><div><dt>Name</dt><dd>{parent.first_name} {parent.last_name}</dd></div><div><dt>Phone</dt><dd>{parent.phone_number}</dd></div><div><dt>Email</dt><dd>{parent.email || 'Not provided'}</dd></div><div><dt>Address</dt><dd>{parent.address || 'Not provided'}</dd></div></dl></section>
    <section className="profile-section"><h2>Account</h2><dl className="detail-grid"><div><dt>Username</dt><dd>{parent.username}</dd></div><div><dt>Password</dt><dd>Managed from Edit Parent</dd></div></dl></section>
    <section className="profile-section"><h2>Children / Dependants</h2>{parent.children.length ? <div className="parent-link-list">{parent.children.map((child) => <div key={child.id}><div><strong>{child.display_name}</strong><span>{child.admission_number} · {child.class_name} · {child.relationship}{child.is_primary_contact ? ' · Primary contact' : ''}</span></div><button type="button" className="text-button" onClick={() => unlinkChild(child.id)}>Unlink</button></div>)}</div> : <p className="muted-copy">No children are linked yet.</p>}
      <form className="parent-link-form" onSubmit={linkChild}><StudentPicker key={pickerKey} label="Search Child" selected={selectedStudent} onChange={chooseStudent} excludeStudentIds={linkedStudentIds} placeholder="Type student name or admission number" />{selectedStudent && <p className="selected-child"><strong>Selected Child:</strong> {selectedStudent.display_name} — {selectedStudent.admission_number} — {selectedStudent.class_name}</p>}<label>Relationship<input name="relationship" value={form.relationship} onChange={change} required /></label><label className="checkbox-label"><input name="is_primary_contact" type="checkbox" checked={form.is_primary_contact} onChange={change} /> Primary contact</label><button disabled={saving}>{saving ? 'Linking…' : 'Link Child'}</button></form>
      {linkError && <p className="form-error" role="alert">{linkError}</p>}
    </section>
  </main>
}
