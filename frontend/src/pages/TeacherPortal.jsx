import { useContext, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AuthContext } from '../auth/context'
import { apiClient, apiDownload } from '../api/client'
import Attribution from '../components/Attribution'
import SortableTable from '../components/SortableTable.jsx'
import AttendancePage from './AttendancePage'
import HomeworkPage from './HomeworkPage'

const sections = [['', 'Dashboard'], ['classes', 'My Classes'], ['attendance', 'Attendance'], ['homework', 'Homework'], ['results', 'Results'], ['comments', 'Report Comments'], ['timetable', 'Timetable'], ['students', 'Students'], ['announcements', 'Announcements'], ['resources', 'Resources'], ['profile', 'Profile']]
const request = (path, data, method = 'POST') => apiClient(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })

export default function TeacherPortal() {
  const { section = '' } = useParams()
  const { user, logout } = useContext(AuthContext)
  const [lookups, setLookups] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { let active = true; apiClient('/teacher/lookups/').then(value => { if (active) setLookups(value) }).catch(() => { if (active) setError('Connect to load teacher assignments.') }); return () => { active = false } }, [])
  return <div className="teacher-portal"><aside className="teacher-sidebar"><h1>Teacher Portal</h1><p>{lookups?.school_name}</p><nav aria-label="Teacher navigation">{sections.map(([path, label]) => <Link key={path} aria-current={section === path ? 'page' : undefined} to={`/teacher${path ? `/${path}` : ''}`}>{label}</Link>)}</nav><button onClick={() => logout('', true)}>Log out</button><Attribution /></aside><main className="teacher-content">{error && <p role="alert">{error}</p>}{section === 'attendance' ? <AttendancePage teacher /> : section === 'homework' ? <HomeworkPage teacher /> : lookups ? <TeacherContent key={section} section={section} lookups={lookups} user={user} /> : <p>Loading assignments…</p>}</main></div>
}

function TeacherContent({ section, lookups, user }) {
  const [items, setItems] = useState([])
  const [notice, setNotice] = useState('')
  const [form, setForm] = useState({})
  const [editing, setEditing] = useState(null)
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [personalTimetable, setPersonalTimetable] = useState(true)
  const [timetableClass, setTimetableClass] = useState('')
  const resources = { students: 'students', results: 'results', comments: 'comments', timetable: 'timetable', announcements: 'announcements', resources: 'resources' }
  const resource = resources[section]
  const timetableItems = items.filter(item => (!timetableClass || item.school_class === Number(timetableClass)) && (!personalTimetable || !item.subject || lookups.subjects.some(s => s.subject === item.subject && s.school_class === item.school_class && s.academic_year === item.academic_year)))
  useEffect(() => { if (!resource) return; let active = true; apiClient(`/teacher/${resource}/`).then(value => { if (active) setItems(value) }).catch(() => { if (active) setNotice('Could not load this section. Connect and try again.') }); return () => { active = false } }, [resource])
  const set = (key, value) => setForm(old => ({ ...old, [key]: value }))
  async function save(event) {
    event.preventDefault(); setBusy(true); setNotice('')
    try {
      const path = `/teacher/${resource}/${editing ? `${editing}/` : ''}`
      if (section === 'resources') {
        const body = new FormData()
        Object.entries(form).forEach(([key, value]) => { if (value !== '') body.append(key, value) })
        if (file) body.append('file', file)
        await apiClient(path, { method: editing ? 'PATCH' : 'POST', body })
      } else await request(path, form, editing ? 'PATCH' : 'POST')
      setItems(await apiClient(`/teacher/${resource}/`)); setForm({}); setEditing(null); setFile(null); setNotice('Saved successfully.')
    } catch (error) { setNotice(Object.values(error.data || {}).flat().join(' ') || 'Save failed.') }
    finally { setBusy(false) }
  }
  async function submitResult(item) {
    try { await request(`/teacher/results/${item.id}/transition/`, { status: 'submitted' }); setItems(await apiClient('/teacher/results/')) }
    catch { setNotice('This result could not be submitted.') }
  }
  const select = (key, label, choices) => <label>{label}<select required value={form[key] || ''} onChange={e => set(key, Number(e.target.value))}><option value="">Select</option>{choices.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
  const enrollments = lookups.enrollments.map(x => ({ id: x.id, name: `${x.student__first_name} ${x.student__last_name} · ${lookups.years.find(y => y.id === x.academic_year)?.name}` }))
  if (!section) return <><TeacherDailyDashboard lookups={lookups} /><p>Attendance still needing completion: {lookups.attendance_pending?.join(', ') || 'None'}</p></>
  if (section === 'classes') return <section><h2>My Classes</h2>{lookups.classes.map(cls => <article className="dashboard-card" key={cls.id}><h3>{cls.name}</h3><p>{lookups.subjects.filter(s => s.school_class === cls.id).map(s => s.subject__name).join(', ') || 'No subjects assigned'}</p>{['students', 'attendance', 'homework', 'results', 'comments', 'announcements', 'resources'].map(path => <Link className="dashboard-link" key={path} to={`/teacher/${path}`}>{sections.find(x => x[0] === path)?.[1]} </Link>)}</article>)}</section>
  if (section === 'profile') return <section><h2>Profile</h2><p>{user.first_name} {user.last_name}</p><p>Username: {user.username}</p><p>Email: {lookups.profile.email || 'Not provided'}</p><Link to="/change-password">Change password</Link></section>
  return <section><h2>{sections.find(x => x[0] === section)?.[1] || 'Teacher Portal'}</h2>{notice && <p role="status">{notice}</p>}{['results', 'comments', 'announcements', 'resources'].includes(section) && <form className="student-form" onSubmit={save}><h3>{editing ? 'Edit Draft' : 'Create'}</h3>{['results', 'comments'].includes(section) && <>{select(section === 'results' ? 'student_enrollment' : 'enrollment', 'Learner enrollment', enrollments)}{select('term', 'Term', lookups.terms)}</>}{section === 'results' && <>{select('class_subject', 'Assigned subject', lookups.subjects.map(s => ({ id: s.id, name: `${lookups.classes.find(c => c.id === s.school_class)?.name} · ${s.subject__name} · ${lookups.years.find(y => y.id === s.academic_year)?.name}` })))}<label>Score<input type="number" step="0.01" min="0" required value={form.score || ''} onChange={e => set('score', e.target.value)} /></label><label>Maximum score<input type="number" step="0.01" min="0.01" required value={form.maximum_score || ''} onChange={e => set('maximum_score', e.target.value)} /></label></>}{['results', 'comments'].includes(section) && <label>Comment<textarea required={section === 'comments'} value={form.comment || ''} onChange={e => set('comment', e.target.value)} /></label>}{['announcements', 'resources'].includes(section) && <label>Title<input maxLength="200" required value={form.title || ''} onChange={e => set('title', e.target.value)} /></label>}{section === 'announcements' && <><label>Message<textarea required value={form.message || ''} onChange={e => set('message', e.target.value)} /></label><label className="checkbox-label"><input type="checkbox" checked={Boolean(form.all_recipients)} onChange={e => set('all_recipients', e.target.checked)} />All My Classes</label>{!form.all_recipients && <label>Selected Assigned Classes<select multiple required value={(form.recipients || []).map(String)} onChange={e => set('recipients', Array.from(e.target.selectedOptions, x => Number(x.value)))}>{lookups.classes.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>}</>}{section === 'resources' && <>{select('school_class', 'Class', lookups.classes)}<label>Assigned subject (optional)<select value={form.class_subject || ''} onChange={e => set('class_subject', e.target.value)}><option value="">Class resource</option>{lookups.subjects.filter(s => s.school_class === Number(form.school_class)).map(s => <option key={s.id} value={s.id}>{s.subject__name}</option>)}</select></label><label>File (PDF, DOCX, PNG, JPG; up to 10 MB)<input type="file" required onChange={e => setFile(e.target.files[0])} accept=".pdf,.docx,.png,.jpg,.jpeg" /></label></>}<button disabled={busy}>{busy ? 'Saving…' : section === 'announcements' ? 'Send Announcement' : 'Save Draft'}</button>{editing && <button type="button" onClick={() => { setEditing(null); setForm({}) }}>Cancel edit</button>}</form>}
    {section === 'students' && <SortableTable className="student-table"><thead><tr><th>Admission Number</th><th>First Name</th><th>Surname</th><th>Class</th><th>Date of Birth</th></tr></thead><tbody>{items.map(s => <tr key={s.id}><td><Link to={`/teacher/students/${s.id}/academic-history`}>{s.admission_number}</Link></td><td>{s.first_name}</td><td>{s.last_name}</td><td>{s.class_name}</td><td>{s.date_of_birth}</td></tr>)}</tbody></SortableTable>}
    {section === 'results' && <SortableTable className="student-table"><thead><tr><th>Learner</th><th>Subject</th><th>Score</th><th>Average %</th><th>Status</th><th>Actions</th></tr></thead><tbody>{items.map(item => <tr key={item.id}><td>{item.student_name}</td><td>{item.subject_name}</td><td>{item.score}</td><td>{item.percentage}</td><td>{item.status}</td><td>{item.status === 'draft' && <><button onClick={() => { setEditing(item.id); setForm({ student_enrollment: item.student_enrollment, term: item.term, class_subject: item.class_subject, score: item.score, maximum_score: item.maximum_score, comment: item.comment }) }}>Edit</button><button onClick={() => submitResult(item)}>Submit for Review</button></>}</td></tr>)}</tbody></SortableTable>}
    {['comments', 'announcements', 'resources'].includes(section) && items.map(item => <article key={item.id} className="dashboard-card"><h3>{item.title || enrollments.find(e => e.id === item.enrollment)?.name}</h3><p>{item.message || item.comment}</p>{section === 'comments' && <button onClick={() => { setEditing(item.id); setForm({ enrollment: item.enrollment, term: item.term, comment: item.comment }) }}>Edit Comment</button>}{section === 'resources' && <button onClick={() => apiDownload(`/teacher/resources/${item.id}/download/`, item.title).catch(() => setNotice('Download failed.'))}>Download Resource</button>}</article>)}
    {section === 'timetable' && <><label>Timetable view<select value={personalTimetable ? 'personal' : 'classes'} onChange={e => setPersonalTimetable(e.target.value === 'personal')}><option value='personal'>Personal teaching timetable</option><option value='classes'>Assigned class timetables</option></select></label><label>Class<select value={timetableClass} onChange={e => setTimetableClass(e.target.value)}><option value=''>All assigned classes</option>{lookups.classes.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label><SortableTable className="student-table"><thead><tr><th>Class</th><th>Day</th><th>Start</th><th>End</th><th>Subject / Activity</th></tr></thead><tbody>{timetableItems.map(item => <tr key={`${item.id}:${item.school_class}`}><td>{item.class_name}</td><td>{item.day_of_week}</td><td>{item.start_time}</td><td>{item.end_time}</td><td>{item.display_label}</td></tr>)}</tbody></SortableTable></>}
  </section>
}

function TeacherDailyDashboard({ lookups }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { let active = true; Promise.all(['homework', 'results', 'timetable', 'announcements'].map(path => apiClient(`/teacher/${path}/`))).then(([homework, results, timetable, announcements]) => { if (active) setData({ homework, results, timetable, announcements }) }).catch(() => { if (active) setError('Daily information could not be loaded. Connect and try again.') }); return () => { active = false } }, [])
  const today = new Date().toLocaleDateString('en-US', { weekday: 'long' })
  return <section><h2>Dashboard</h2><p>{lookups.classes.length} assigned classes</p>{error && <p role="alert">{error}</p>}{data && <><h3>Today’s timetable</h3>{data.timetable.filter(t => t.day_of_week === today).map(t => <p key={t.id}>{t.start_time} – {t.end_time}: {t.class_name} · {t.display_label}</p>)}<Link to="/teacher/attendance">Complete today’s attendance</Link><p>Homework in Draft: {data.homework.filter(h => h.status === 'draft').length}</p><p>Draft results: {data.results.filter(r => r.status === 'draft').length} · Submitted for Review: {data.results.filter(r => r.status === 'submitted').length}</p><h3>Recent homework</h3>{data.homework.slice(0, 5).map(h => <p key={h.id}>{h.title} · Due {h.due_date} · {h.status}</p>)}<h3>Announcements</h3>{data.announcements.slice(0, 5).map(a => <article key={a.id}><strong>{a.title}</strong><p>{a.message}</p></article>)}</>}</section>
}
