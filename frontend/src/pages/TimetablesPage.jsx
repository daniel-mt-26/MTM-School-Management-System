import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getAcademicRecords, saveAcademicRecord } from '../api/academics'
import TimetableEditor from '../components/TimetableEditor'
import { emptyEntry } from '../components/timetableDefaults.js'

const blank = () => ({ name: '', academic_year: '', term: '', classes: [], entries: [emptyEntry()] })
export default function TimetablesPage() {
  const [lookups, setLookups] = useState({ classes: [], years: [], terms: [], subjects: [], activities: [] })
  const [items, setItems] = useState([])
  const [form, setForm] = useState(blank)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    Promise.all(['classes', 'academic-years', 'terms', 'subjects', 'subjects/library', 'timetable-plans'].map((resource) => getAcademicRecords(resource)))
      .then(([classes, years, terms, subjects, library, plans]) => { setLookups({ classes, years, terms, subjects, activities: library.activities }); setItems(plans) })
      .catch(() => setError('Timetable setup could not be loaded.'))
  }, [])
  async function save(event) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('')
    try {
      await saveAcademicRecord('timetable-plans', form, form.id)
      setItems(await getAcademicRecords('timetable-plans')); setForm(blank()); setNotice('Timetable saved for all selected classes.')
    } catch (e) { setError(Object.values(e.data || {}).flat().join(' ') || 'Timetable could not be saved.') }
    finally { setBusy(false) }
  }
  return <main className="student-page"><Link to="/school/academics">Back to Academics</Link><h1>Timetables</h1><Link to="/school/academics/curriculum">Subject Settings / Curriculum Setup</Link><p>Share one timetable across selected classes. Subject choices come from your school’s active curriculum.</p>
    <TimetableEditor form={form} setForm={setForm} lookups={lookups} onSave={save} busy={busy} error={error} />{notice && <p role="status">{notice}</p>}
    {items.map((item) => <section className="profile-section" key={item.id}><h2>{item.name}</h2><p>{item.class_names.join(', ')} · {item.academic_year_name} / {item.term_name}</p><button type="button" onClick={() => { setForm(item); setError(''); setNotice('') }}>Edit {item.name}</button><ul>{item.entries.map((row) => <li key={row.id}>{row.day_of_week} {row.start_time.slice(0, 5)}–{row.end_time.slice(0, 5)}: {row.subject ? lookups.subjects.find((s) => s.id === row.subject)?.name : row.label}</li>)}</ul></section>)}
  </main>
}
