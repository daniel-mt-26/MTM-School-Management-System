import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiClient } from '../api/client'

export default function TeacherAnnouncementsPage() {
  const [teachers, setTeachers] = useState([])
  const [form, setForm] = useState({ title: '', message: '', all_recipients: true, recipients: [] })
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { apiClient('/school/teachers/').then(setTeachers).catch(() => setNotice('Could not load teachers.')) }, [])
  async function send(event) {
    event.preventDefault(); setBusy(true)
    try { await apiClient('/school/teacher-announcements/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form) }); setNotice('Announcement sent to teachers.'); setForm(old => ({ ...old, title: '', message: '' })) }
    catch (error) { setNotice(Object.values(error.data || {}).flat().join(' ') || 'Send failed.') }
    finally { setBusy(false) }
  }
  return <main className="student-page"><Link to="/app">Back to School Dashboard</Link><h1>Teacher Announcements</h1><form className="student-form" onSubmit={send}><label>Title<input required maxLength="200" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} /></label><label>Message<textarea required value={form.message} onChange={e => setForm({ ...form, message: e.target.value })} /></label><label className="checkbox-label"><input type="checkbox" checked={form.all_recipients} onChange={e => setForm({ ...form, all_recipients: e.target.checked })} />All Teachers</label>{!form.all_recipients && <label>Selected Teachers<select multiple required value={form.recipients.map(String)} onChange={e => setForm({ ...form, recipients: Array.from(e.target.selectedOptions, x => Number(x.value)) })}>{teachers.filter(t => t.is_active).map(t => <option key={t.id} value={t.id}>{t.first_name} {t.last_name}</option>)}</select></label>}<button disabled={busy}>Send Announcement</button></form>{notice && <p role="status">{notice}</p>}</main>
}
