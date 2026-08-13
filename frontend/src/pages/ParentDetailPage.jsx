import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getStudents } from '../api/students'
import { getParent, linkParentChild, unlinkParentChild } from '../api/parents'

export default function ParentDetailPage() {
  const { parentId } = useParams()
  const [parent, setParent] = useState(null)
  const [students, setStudents] = useState([])
  const [form, setForm] = useState({ student: '', relationship: 'Guardian', is_primary_contact: false })
  const [error, setError] = useState('')
  const [linkError, setLinkError] = useState('')
  const [saving, setSaving] = useState(false)
  const load = useCallback(() => getParent(parentId).then(setParent), [parentId])

  useEffect(() => { Promise.all([load(), getStudents()]).then(([, schoolStudents]) => setStudents(schoolStudents)).catch(() => setError('We could not load this parent profile.')) }, [load])
  const availableStudents = useMemo(() => { const linked = new Set(parent?.children.map((child) => child.student) || []); return students.filter((student) => !linked.has(student.id)) }, [parent, students])
  function change(event) { const { name, type, checked, value } = event.target; setForm((current) => ({ ...current, [name]: type === 'checkbox' ? checked : value })) }
  async function linkChild(event) { event.preventDefault(); setLinkError(''); setSaving(true); try { await linkParentChild({ ...form, parent: Number(parentId), student: Number(form.student) }); await load(); setForm({ student: '', relationship: 'Guardian', is_primary_contact: false }) } catch (requestError) { setLinkError(Object.values(requestError.data || {}).flat().join(' ') || 'We could not link this child. Check the relationship and primary contact setting.') } finally { setSaving(false) } }
  async function unlinkChild(id) { setLinkError(''); try { await unlinkParentChild(id); await load() } catch { setLinkError('We could not unlink this child.') } }

  if (!parent && !error) return <main className="school-profile-state">Loading parent…</main>
  if (error || !parent) return <main className="school-profile-state" role="alert"><p>{error || 'Parent not found.'}</p><Link to="/school/parents" className="dashboard-link">Back to Parents</Link></main>
  return <main className="student-page"><header className="student-page-header"><div><Link to="/school/parents" className="dashboard-link">Back to Parents</Link><h1>{parent.first_name} {parent.last_name}</h1></div><Link to={`/school/parents/${parent.id}/edit`} className="primary-link">Edit Parent</Link></header>
    <section className="profile-section"><h2>Parent Details</h2><dl className="detail-grid"><div><dt>Name</dt><dd>{parent.first_name} {parent.last_name}</dd></div><div><dt>Phone</dt><dd>{parent.phone_number}</dd></div><div><dt>Email</dt><dd>{parent.email || 'Not provided'}</dd></div><div><dt>Address</dt><dd>{parent.address || 'Not provided'}</dd></div></dl></section>
    <section className="profile-section"><h2>Account</h2><dl className="detail-grid"><div><dt>Username</dt><dd>{parent.username}</dd></div><div><dt>Password</dt><dd>Managed from Edit Parent</dd></div></dl></section>
    <section className="profile-section"><h2>Children / Dependants</h2>{parent.children.length ? <div className="parent-link-list">{parent.children.map((child) => <div key={child.id}><div><strong>{child.display_name}</strong><span>{child.admission_number} · {child.class_name} · {child.relationship}{child.is_primary_contact ? ' · Primary contact' : ''}</span></div><button type="button" className="text-button" onClick={() => unlinkChild(child.id)}>Unlink</button></div>)}</div> : <p className="muted-copy">No children are linked yet.</p>}
      {availableStudents.length ? <form className="parent-link-form" onSubmit={linkChild}><select name="student" value={form.student} onChange={change} required><option value="">Choose a student</option>{availableStudents.map((student) => <option key={student.id} value={student.id}>{student.display_name} · {student.admission_number} · {student.class_name}</option>)}</select><input name="relationship" value={form.relationship} onChange={change} placeholder="Relationship" required /><label className="checkbox-label"><input name="is_primary_contact" type="checkbox" checked={form.is_primary_contact} onChange={change} /> Primary contact</label><button disabled={saving}>{saving ? 'Linking…' : 'Link Child'}</button></form> : <p className="muted-copy">All current-school students are already linked to this parent.</p>}
      {linkError && <p className="form-error" role="alert">{linkError}</p>}
    </section>
  </main>
}
