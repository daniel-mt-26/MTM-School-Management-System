import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getAcademicRecords, saveAcademicRecord } from '../api/academics'

export default function CurriculumPage() {
  const [library, setLibrary] = useState([])
  const [subjects, setSubjects] = useState([])
  const [selected, setSelected] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { Promise.all([getAcademicRecords('subjects/library'), getAcademicRecords('subjects')]).then(([data, existing]) => { setLibrary(data.groups); setSubjects(existing) }).catch(() => setError('Curriculum could not be loaded.')) }, [])
  async function change(action) { setBusy(true); setError(''); try { await action(); setSubjects(await getAcademicRecords('subjects')); setSelected([]) } catch (e) { setError(Object.values(e.data || {}).flat().join(' ') || 'Subject settings could not be saved.') } finally { setBusy(false) } }
  return <main className="student-page"><Link to="/school/academics/timetables">Back to Timetables</Link><h1>Subject Settings / Curriculum Setup</h1><p>Choose the subjects your school teaches. Built-in options are optional; existing custom subjects are preserved.</p>{error && <p role="alert">{error}</p>}
    {library.map((group) => <fieldset key={group.name}><legend>{group.name}</legend>{group.subjects.map((item) => { const active = subjects.some((s) => s.name.toLowerCase() === item.name.toLowerCase() && s.is_active); return <label key={item.key}><input type="checkbox" disabled={active || busy} checked={active || selected.includes(item.key)} onChange={(e) => setSelected((old) => e.target.checked ? [...new Set([...old, item.key])] : old.filter((key) => key !== item.key))} />{item.name}{active && ' (active)'}</label> })}</fieldset>)}
    <button disabled={busy || !selected.length} onClick={() => change(() => saveAcademicRecord('subjects/activate', { keys: selected }))}>Activate selected subjects</button>
    <h2>School subjects</h2>{subjects.map((s) => <p key={s.id}>{s.name} · {s.is_active ? 'Active' : 'Inactive'} <button disabled={busy} onClick={() => change(() => saveAcademicRecord('subjects', { is_active: !s.is_active }, s.id))}>{s.is_active ? 'Deactivate' : 'Activate'} {s.name}</button></p>)}
    <Link to="/school/academics/subjects">Manage custom subjects</Link> · <Link to="/school/academics/class-subjects">Manage class subject assignments</Link>
  </main>
}
