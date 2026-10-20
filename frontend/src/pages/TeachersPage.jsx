import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiClient } from '../api/client'
import TemporaryPassword from '../components/TemporaryPassword'
import SortableTable from '../components/SortableTable.jsx'

const blank = { first_name: '', last_name: '', email: '', assignments: [] }
export default function TeachersPage() {
  const [teachers, setTeachers] = useState([])
  const [classes, setClasses] = useState([])
  const [subjects, setSubjects] = useState([])
  const [form, setForm] = useState(blank)
  const [editing, setEditing] = useState(null)
  const [credentials, setCredentials] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { Promise.all(['/school/teachers/', '/school/classes/', '/school/class-subjects/'].map(path => apiClient(path))).then(([t, c, s]) => { setTeachers(t); setClasses(c); setSubjects(s) }).catch(() => setError('Teacher administration could not be loaded.')) }, [])
  async function mutate(path, body, method = 'POST') {
    setBusy(true); setError(''); setCredentials(null)
    try {
      const value = await apiClient(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      if (value.temporary_password) setCredentials(value)
      setTeachers(await apiClient('/school/teachers/')); return value
    } catch (error) { setError(Object.values(error.data || {}).flat().join(' ') || 'Action failed.') }
    finally { setBusy(false) }
  }
  async function save(event) {
    event.preventDefault()
    if (await mutate(`/school/teachers/${editing ? `${editing}/` : ''}`, form, editing ? 'PATCH' : 'POST')) { setForm(blank); setEditing(null) }
  }
  function assignment(classId, checked) {
    setForm(old => ({ ...old, assignments: checked ? [...old.assignments, { school_class: classId, subjects: [] }] : old.assignments.filter(a => a.school_class !== classId) }))
  }
  return <main className="student-page"><Link to="/app">Back to School Dashboard</Link><h1>Teachers</h1>{error && <p role="alert">{error}</p>}{credentials && <TemporaryPassword username={credentials.username} password={credentials.temporary_password} onDismiss={() => setCredentials(null)} />}<form className="student-form" onSubmit={save}><h2>{editing ? 'Edit Teacher' : 'Create Teacher Account'}</h2>{['first_name', 'last_name', 'email'].map(key => <label key={key}>{key.replace('_', ' ')}<input type={key === 'email' ? 'email' : 'text'} required={key !== 'email'} value={form[key]} onChange={e => setForm(old => ({ ...old, [key]: e.target.value }))} /></label>)}<fieldset><legend>Class and Subject Assignments</legend>{classes.map(cls => {
    const current = form.assignments.find(a => a.school_class === cls.id)
    return <div key={cls.id}><label className="checkbox-label"><input type="checkbox" checked={Boolean(current)} onChange={e => assignment(cls.id, e.target.checked)} />{cls.name}</label>{current && <label>Subjects (select each authorized class/year subject)<select multiple value={current.subjects.map(String)} onChange={e => { const selected = Array.from(e.target.selectedOptions, x => Number(x.value)); setForm(old => ({ ...old, assignments: old.assignments.map(a => a.school_class === cls.id ? { ...a, subjects: selected } : a) })) }}>{subjects.filter(s => s.school_class === cls.id).map(s => <option key={s.id} value={s.id}>{s.subject_name || s.subject} · {s.academic_year_name || s.academic_year}</option>)}</select></label>}</div>
  })}</fieldset><button disabled={busy}>{editing ? 'Save Changes' : 'Create with Temporary Password'}</button>{editing && <button type="button" onClick={() => { setEditing(null); setForm(blank) }}>Cancel</button>}</form><SortableTable className="student-table"><thead><tr><th>Name</th><th>Username</th><th>Status</th><th>Last Login</th><th>Assignments</th><th>Actions</th></tr></thead><tbody>{teachers.map(t => <tr key={t.id}><td>{t.first_name} {t.last_name}</td><td>{t.username}</td><td>{t.is_active ? 'Active' : 'Inactive'}</td><td>{t.last_login || 'Never'}</td><td>{t.assignments.map(a => `${a.class_name} (${a.subjects.length} subjects)`).join(', ')}</td><td><button disabled={busy} onClick={() => { setEditing(t.id); setForm({ first_name: t.first_name, last_name: t.last_name, email: t.email, assignments: t.assignments.map(a => ({ school_class: a.school_class, subjects: a.subjects })) }) }}>Edit / Assign</button><button disabled={busy} onClick={() => mutate(`/school/teachers/${t.id}/`, { is_active: !t.is_active }, 'PATCH')}>{t.is_active ? 'Deactivate' : 'Activate'}</button><button disabled={busy} onClick={() => mutate(`/school/teachers/${t.id}/reset-password/`, {})}>Reset Password</button></td></tr>)}</tbody></SortableTable></main>
}
