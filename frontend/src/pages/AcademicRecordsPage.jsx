import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { downloadReportCard, getAcademicRecords, removeAcademicRecord, saveAcademicRecord } from '../api/academics'
import StudentPicker from '../components/StudentPicker'

const titles = { classes: 'Classes', subjects: 'Subjects', 'academic-years': 'Academic Years', terms: 'Terms', enrollments: 'Enrolments', 'class-subjects': 'Class Subjects', timetables: 'Timetables', results: 'Results', 'report-cards': 'Report Cards' }
const blank = { classes: { name: '', is_active: true }, subjects: { name: '', code: '', is_active: true }, 'academic-years': { name: '', start_date: '', end_date: '', is_current: false }, terms: { academic_year: '', name: '', sequence: '1', start_date: '', end_date: '' }, 'class-subjects': { school_class: '', subject: '', academic_year: '' }, timetables: { school_class: '', academic_year: '', term: '', day_of_week: 'Monday', start_time: '', end_time: '', subject: '', label: '' }, results: { student_enrollment: '', term: '', class_subject: '', score: '', maximum_score: '', comment: '' }, 'report-cards': { student_enrollment: '', term: '' } }
const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']

function option(items, value, label, placeholder) { return <select value={value} onChange={(e) => label.onChange(e.target.value)} required><option value="">{placeholder}</option>{items.map((item) => <option key={item.id} value={item.id}>{label.text(item)}</option>)}</select> }
function errorText(error) { return Object.values(error?.data || {}).flat().join(' ') || 'We could not save this record. Check the highlighted values and try again.' }

export default function AcademicRecordsPage() {
  const { resource } = useParams()
  return <AcademicResourcePage key={resource} resource={resource} />
}

function AcademicResourcePage({ resource }) {
  const title = titles[resource] || 'Academics'
  const readOnly = resource === 'enrollments'
  const [items, setItems] = useState([])
  const [lookups, setLookups] = useState({ classes: [], subjects: [], years: [], terms: [], enrollments: [], students: [], assignments: [] })
  const [form, setForm] = useState(blank[resource] || {})
  const [editing, setEditing] = useState(null)
  const [filters, setFilters] = useState({ academic_year: '', term: '', school_class: '', subject: '', student: '', open: '' })
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const set = (name, value) => setForm((current) => ({ ...current, [name]: value }))
  const loadLookups = useCallback(async () => {
    const [classes, subjects, years, terms, enrollments, students, assignments] = await Promise.all([
      getAcademicRecords('classes'), getAcademicRecords('subjects'), getAcademicRecords('academic-years'), getAcademicRecords('terms'), getAcademicRecords('enrollments'), getAcademicRecords('students'), getAcademicRecords('class-subjects'),
    ])
    setLookups({ classes, subjects, years, terms, enrollments, students, assignments })
  }, [])
  const load = useCallback(async () => { setLoading(true); setError(''); try { setItems(await getAcademicRecords(resource, ['enrollments', 'results', 'report-cards', 'timetables', 'class-subjects'].includes(resource) ? filters : {})) } catch { setError('We could not load these academic records.') } finally { setLoading(false) } }, [resource, filters])
  useEffect(() => {
    Promise.resolve().then(loadLookups).catch(() => setError('Some selection lists could not be loaded.'))
    getAcademicRecords(resource).then(setItems).catch(() => setError('We could not load these academic records.')).finally(() => setLoading(false))
  }, [resource, loadLookups])
  useEffect(() => {
    if (!['enrollments', 'results', 'report-cards', 'timetables', 'class-subjects'].includes(resource)) return
    getAcademicRecords(resource, filters).then(setItems).catch(() => setError('We could not load these academic records.')).finally(() => setLoading(false))
  }, [filters, resource])
  useEffect(() => {
    if (!['classes', 'subjects'].includes(resource)) return
    const timer = setTimeout(() => getAcademicRecords(resource, { q: query.trim() }).then(setItems).catch(() => setError(`We could not search ${title.toLowerCase()}.`)), 250)
    return () => clearTimeout(timer)
  }, [query, resource, title])
  const terms = useMemo(() => lookups.terms.filter((term) => !form.academic_year || String(term.academic_year) === String(form.academic_year)), [lookups.terms, form.academic_year])
  const assignedSubjects = useMemo(() => lookups.assignments.filter((item) => (!form.school_class || String(item.school_class) === String(form.school_class)) && (!form.academic_year || String(item.academic_year) === String(form.academic_year))), [lookups.assignments, form.school_class, form.academic_year])
  const filteredEnrollments = useMemo(() => lookups.enrollments.filter((item) => (!form.academic_year || String(item.academic_year) === String(form.academic_year)) && (!form.school_class || String(item.school_class) === String(form.school_class))), [lookups.enrollments, form.academic_year, form.school_class])

  async function submit(event) { event.preventDefault(); setError(''); try { const payload = { ...form }; Object.keys(payload).forEach((key) => { if (['academic_year', 'school_class', 'subject', 'term', 'student_enrollment', 'class_subject'].includes(key) && payload[key] !== '') payload[key] = Number(payload[key]) }); if (resource === 'timetables' && payload.subject === '') delete payload.subject; await saveAcademicRecord(resource, payload, editing?.id); setEditing(null); setForm(blank[resource]); await Promise.all([load(), loadLookups()]) } catch (requestError) { setError(errorText(requestError)) } }
  function edit(item) { const value = { ...item }; Object.keys(blank[resource] || {}).forEach((key) => { if (value[key] === null || value[key] === undefined) value[key] = '' }); setEditing(item); setForm(value); window.scrollTo({ top: 0, behavior: 'smooth' }) }
  async function remove(id) { if (!window.confirm('Remove this record? This cannot be undone.')) return; try { await removeAcademicRecord(resource, id); await load() } catch { setError('This record cannot be removed because it is in use or protected.') } }
  const filterControl = (name, label, choices, text) => <label>{label}<select value={filters[name]} onChange={(e) => setFilters((current) => ({ ...current, [name]: e.target.value }))}><option value="">All</option>{choices.map((item) => <option key={item.id} value={item.id}>{text(item)}</option>)}</select></label>

  if (!titles[resource]) return <main className="school-profile-state">This academic area does not exist.</main>
  return <main className="student-page"><header className="student-page-header"><div><Link to="/school/academics" className="dashboard-link">Back to Academics</Link><h1>{title}</h1><p>{resource === 'enrollments' ? 'Historical enrolment records are read-only; use student transfers for class changes.' : 'Manage records for the authenticated school only.'}</p></div></header>
    {['classes', 'subjects'].includes(resource) && <input className="parent-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`Search ${title.toLowerCase()}`} />}
    {resource === 'class-subjects' && <div className="academic-filters">{filterControl('academic_year', 'Academic Year', lookups.years, (item) => item.name)}{filterControl('school_class', 'Class', lookups.classes, (item) => item.name)}</div>}
    {(resource === 'enrollments' || resource === 'results' || resource === 'report-cards' || resource === 'timetables') && <div className="academic-filters">{filterControl('academic_year', 'Academic Year', lookups.years, (item) => item.name)}{(resource === 'results' || resource === 'report-cards' || resource === 'timetables') && filterControl('term', 'Term', lookups.terms.filter((term) => !filters.academic_year || String(term.academic_year) === String(filters.academic_year)), (item) => item.name)}{(resource === 'enrollments' || resource === 'results' || resource === 'timetables') && <label>Class<select value={filters.school_class} onChange={(event) => setFilters((current) => ({ ...current, school_class: event.target.value, student: '' }))}><option value="">All</option>{lookups.classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}{resource === 'results' && <>{filterControl('subject', 'Subject', lookups.subjects, (item) => item.name)}<StudentPicker key={filters.school_class || 'all-classes'} selected={lookups.students.find((item) => String(item.id) === String(filters.student))} schoolClass={filters.school_class} onChange={(student) => setFilters((current) => ({ ...current, student: student ? String(student.id) : '' }))} /></>}{resource === 'enrollments' && <label>Current Status<select value={filters.open} onChange={(e) => setFilters((current) => ({ ...current, open: e.target.value }))}><option value="">All</option><option value="true">Open</option><option value="false">Closed</option></select></label>}</div>}
    {!readOnly && <form className="student-form academic-form" onSubmit={submit}><h2>{editing ? `Edit ${title.slice(0, -1)}` : `Add ${title.slice(0, -1)}`}</h2><AcademicFields resource={resource} form={form} set={set} lookups={lookups} terms={terms} assignedSubjects={assignedSubjects} enrollments={filteredEnrollments} />{error && <p className="form-error">{error}</p>}<div className="settings-actions"><button>{editing ? 'Save Changes' : 'Add Record'}</button>{editing && <button type="button" className="secondary-button" onClick={() => { setEditing(null); setForm(blank[resource]) }}>Cancel Edit</button>}</div></form>}
    {loading ? <div className="student-state">Loading {title.toLowerCase()}…</div> : <AcademicTable resource={resource} items={resource === 'timetables' && (!filters.academic_year || !filters.term || !filters.school_class) ? [] : items} onEdit={edit} onRemove={remove} />}
  </main>
}

function AcademicFields({ resource, form, set, lookups, terms, assignedSubjects, enrollments }) {
  const input = (name, label, type = 'text', extra = {}) => <label>{label}<input type={type} value={form[name] ?? ''} onChange={(e) => set(name, e.target.value)} {...extra} /></label>
  const select = (name, label, values, text, placeholder) => <label>{label}{option(values, form[name] ?? '', { onChange: (value) => set(name, value), text }, placeholder)}</label>
  if (resource === 'classes') return <><div className="form-columns">{input('name', 'Class Name')}</div><label className="checkbox-label"><input type="checkbox" checked={form.is_active} onChange={(e) => set('is_active', e.target.checked)} /> Active class</label></>
  if (resource === 'subjects') return <><div className="form-columns">{input('name', 'Subject Name')}{input('code', 'Subject Code')}</div><label className="checkbox-label"><input type="checkbox" checked={form.is_active} onChange={(e) => set('is_active', e.target.checked)} /> Active subject</label></>
  if (resource === 'academic-years') return <><div className="form-columns">{input('name', 'Academic Year')}{input('start_date', 'Start Date', 'date')}</div>{input('end_date', 'End Date', 'date')}<label className="checkbox-label"><input type="checkbox" checked={form.is_current} onChange={(e) => set('is_current', e.target.checked)} /> Current academic year</label></>
  if (resource === 'terms') return <><div className="form-columns">{select('academic_year', 'Academic Year', lookups.years, (item) => item.name, 'Choose academic year')}{input('name', 'Term Name')}</div><div className="form-columns">{input('sequence', 'Term Order', 'number', { min: '1' })}{input('start_date', 'Start Date', 'date')}</div>{input('end_date', 'End Date', 'date')}</>
  if (resource === 'class-subjects') return <div className="form-columns">{select('academic_year', 'Academic Year', lookups.years, (item) => item.name, 'Choose academic year')}{select('school_class', 'Class', lookups.classes, (item) => item.name, 'Choose class')}{select('subject', 'Subject', lookups.subjects, (item) => item.name, 'Choose subject')}</div>
  if (resource === 'timetables') { const timetableSubjects = Array.from(new Map(assignedSubjects.map((item) => [item.subject, { id: item.subject, name: item.subject_name }])).values()); return <><div className="form-columns">{select('academic_year', 'Academic Year', lookups.years, (item) => item.name, 'Choose academic year')}{select('term', 'Term', terms, (item) => item.name, 'Choose term')}{select('school_class', 'Class', lookups.classes, (item) => item.name, 'Choose class')}</div><div className="form-columns"><label>Day<select value={form.day_of_week} onChange={(e) => set('day_of_week', e.target.value)}>{days.map((day) => <option key={day}>{day}</option>)}</select></label>{input('start_time', 'Start Time', 'time')}{input('end_time', 'End Time', 'time')}</div><div className="form-columns">{select('subject', 'Subject (optional)', timetableSubjects, (item) => item.name, 'Use a label instead')}<label>Label for Break, Lunch, or Assembly<textarea value={form.label} onChange={(e) => set('label', e.target.value)} rows="2" /></label></div></> }
  if (resource === 'results') return <><div className="form-columns">{select('student_enrollment', 'Student Enrolment', enrollments, (item) => `${item.student_name} · ${item.class_name} · ${item.academic_year_name}`, 'Choose enrolment')}{select('term', 'Term', terms, (item) => `${item.academic_year_name} · ${item.name}`, 'Choose term')}</div><div className="form-columns">{select('class_subject', 'Class Subject', assignedSubjects, (item) => item.subject_name, 'Choose subject')}{input('score', 'Score', 'number', { min: '0', step: '0.01' })}{input('maximum_score', 'Maximum Score', 'number', { min: '0.01', step: '0.01' })}</div><label>Comment<textarea value={form.comment} onChange={(e) => set('comment', e.target.value)} rows="3" /></label></>
  if (resource === 'report-cards') return <div className="form-columns">{select('student_enrollment', 'Student Enrolment', enrollments, (item) => `${item.student_name} · ${item.class_name} · ${item.academic_year_name}`, 'Choose enrolment')}{select('term', 'Term', terms, (item) => `${item.academic_year_name} · ${item.name}`, 'Choose term')}</div>
  return null
}

function AcademicTable({ resource, items, onEdit, onRemove }) {
  if (resource === 'timetables') return <TimetableGrid entries={items} onEdit={onEdit} onRemove={onRemove} />
  const rows = {
    classes: { heads: ['Class', 'Status'], cells: (x) => [x.name, x.is_active ? 'Active' : 'Inactive'] }, subjects: { heads: ['Subject', 'Code', 'Status'], cells: (x) => [x.name, x.code, x.is_active ? 'Active' : 'Inactive'] }, 'academic-years': { heads: ['Year', 'Dates', 'Status'], cells: (x) => [x.name, `${x.start_date} – ${x.end_date}`, x.is_current ? 'Current' : 'Historical'] }, terms: { heads: ['Term', 'Academic Year', 'Dates'], cells: (x) => [x.name, x.academic_year_name, `${x.start_date} – ${x.end_date}`] }, 'class-subjects': { heads: ['Class', 'Subject', 'Academic Year'], cells: (x) => [x.class_name, x.subject_name, x.academic_year_name] }, enrollments: { heads: ['Student', 'Class', 'Academic Year', 'Enrolled', 'Left / Status'], cells: (x) => [`${x.student_name} (${x.admission_number})`, x.class_name, x.academic_year_name, x.enrolled_on, x.left_on || 'Open'] }, timetables: { heads: ['Day', 'Time', 'Class', 'Year / Term', 'Entry'], cells: (x) => [x.day_of_week, `${x.start_time} – ${x.end_time}`, x.class_name, `${x.academic_year_name} · ${x.term_name}`, x.display_label] }, results: { heads: ['Student', 'Class', 'Term', 'Subject', 'Mark'], cells: (x) => [`${x.student_name} (${x.admission_number})`, x.class_name, `${x.academic_year_name} · ${x.term_name}`, x.subject_name, `${x.score}/${x.maximum_score} (${x.percentage}%)`] }, 'report-cards': { heads: ['Student', 'Class', 'Year / Term', 'Generated', 'File'], cells: (x) => [`${x.student_name} (${x.admission_number})`, x.class_name, `${x.academic_year_name} · ${x.term_name}`, new Date(x.generated_at).toLocaleDateString(), x.download_url ? <button className="inline-button" onClick={() => downloadReportCard(x.id)}>Download Report Card</button> : 'No file available'] } }[resource]
  const removable = ['class-subjects', 'timetables'].includes(resource)
  return <div className="student-table-wrap"><table className="student-table"><thead><tr>{rows.heads.map((head) => <th key={head}>{head}</th>)}{resource !== 'enrollments' && <th>Actions</th>}</tr></thead><tbody>{items.length ? items.map((item) => <tr key={item.id}>{rows.cells(item).map((cell, index) => <td key={index}>{cell}</td>)}{resource !== 'enrollments' && <td><button className="inline-button" onClick={() => onEdit(item)}>Edit</button>{removable && <button className="text-button" onClick={() => onRemove(item.id)}>Remove</button>}</td>}</tr>) : <tr><td className="empty-cell" colSpan={rows.heads.length + (resource !== 'enrollments' ? 1 : 0)}>No records match the current selection.</td></tr>}</tbody></table></div>
}

function TimetableGrid({ entries, onEdit, onRemove }) {
  const slots = Array.from(new Set(entries.map((entry) => `${entry.start_time} – ${entry.end_time}`))).sort()
  const entryAt = (slot, day) => entries.find((entry) => `${entry.start_time} – ${entry.end_time}` === slot && entry.day_of_week === day)
  return <div className="student-table-wrap timetable-grid"><table className="student-table"><thead><tr><th>Time</th>{days.map((day) => <th key={day}>{day}</th>)}</tr></thead><tbody>{slots.length ? slots.map((slot) => <tr key={slot}><th>{slot}</th>{days.map((day) => { const entry = entryAt(slot, day); return <td key={day}>{entry && <div className="timetable-cell"><strong>{entry.display_label}</strong><span>{entry.class_name}</span><button className="inline-button" onClick={() => onEdit(entry)}>Edit</button><button className="text-button" onClick={() => onRemove(entry.id)}>Delete</button></div>}</td> })}</tr>) : <tr><td colSpan="6" className="empty-cell">Choose an academic year, term, and class to view its timetable.</td></tr>}</tbody></table></div>
}
