import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  createAnnouncement,
  getAnnouncements,
  getCommunicationHistory,
  getCommunicationSettings,
  previewAnnouncement,
  sendAnnouncement,
  sendFeeReminders,
  updateCommunicationSettings,
} from '../api/communication'
import { getParents } from '../api/parents'
import { getSchoolClasses } from '../api/students'
import StudentPicker from '../components/StudentPicker'

const navigation = [['announcements', 'Announcements'], ['fee-reminders', 'Fee Reminders'], ['history', 'History'], ['settings', 'Settings']]
const initialAnnouncement = { title: '', message: '', audience: 'all_parents', school_class: '', student: '', parent: '', channels: ['in_app'] }

export default function CommunicationPage() {
  const { section = 'announcements' } = useParams()
  const [settings, setSettings] = useState(null)
  const [announcements, setAnnouncements] = useState([])
  const [history, setHistory] = useState([])
  const [classes, setClasses] = useState([])
  const [parents, setParents] = useState([])
  const [form, setForm] = useState(initialAnnouncement)
  const [draft, setDraft] = useState(null)
  const [selectedAnnouncementStudent, setSelectedAnnouncementStudent] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    let active = true
    Promise.all([getCommunicationSettings(), getAnnouncements(), getCommunicationHistory(), getSchoolClasses(), getParents()])
      .then(([nextSettings, nextAnnouncements, nextHistory, nextClasses, nextParents]) => {
        if (!active) return
        setSettings(nextSettings); setAnnouncements(nextAnnouncements); setHistory(nextHistory)
        setClasses(nextClasses); setParents(nextParents)
      })
      .catch(() => active && setError('We could not load communication data. Please try again.'))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [])

  const setField = (event) => setForm((current) => ({ ...current, [event.target.name]: event.target.value }))
  const toggleChannel = (channel) => setForm((current) => ({ ...current, channels: current.channels.includes(channel) ? current.channels.filter((item) => item !== channel) : [...current.channels, channel] }))
  const reloadHistory = () => getCommunicationHistory().then(setHistory).catch(() => setError('We could not refresh communication history.'))

  async function saveDraft(event) {
    event.preventDefault(); setError(''); setNotice('')
    try {
      const payload = { ...form, school_class: form.audience === 'class' ? Number(form.school_class) : null, student: form.audience === 'student' ? Number(form.student) : null, parent: form.audience === 'parent' ? Number(form.parent) : null }
      const created = await createAnnouncement(payload)
      const preview = await previewAnnouncement(created.id)
      setDraft({ ...created, recipient_count: preview.recipient_count })
      setAnnouncements((items) => [created, ...items])
      setNotice(`Draft saved. Review and confirm sending to ${preview.recipient_count} parent${preview.recipient_count === 1 ? '' : 's'}.`)
    } catch {
      setError('The announcement could not be saved. Check the audience and required fields.')
    }
  }

  async function confirmSend() {
    if (!draft) return
    try {
      const sent = await sendAnnouncement(draft.id)
      setAnnouncements((items) => items.map((item) => item.id === sent.id ? { ...item, ...sent } : item))
      setForm(initialAnnouncement); setSelectedAnnouncementStudent(null); setDraft(null); setNotice(`Announcement sent to ${sent.recipient_count} parent${sent.recipient_count === 1 ? '' : 's'}.`); reloadHistory()
    } catch { setError('The announcement could not be sent.') }
  }

  async function generateReminders() {
    try { const result = await sendFeeReminders(); setNotice(`Created ${result.messages_created} local communication record(s) for ${result.students_considered} eligible student(s).`); reloadHistory() } catch { setError('Fee reminders could not be generated.') }
  }

  async function saveSettings(event) {
    event.preventDefault()
    try { setSettings(await updateCommunicationSettings(settings)); setNotice('Communication settings saved.') } catch { setError('Communication settings could not be saved.') }
  }

  if (loading) return <main className="school-profile-state">Loading communication…</main>
  return <main className="student-page"><header className="student-page-header"><div><Link to="/school" className="dashboard-link">← Back to School Dashboard</Link><h1>Communication</h1><p>Parent notifications and delivery history. WhatsApp is queued only for eligible opt-in contacts.</p></div></header>
    <nav className="communication-nav">{navigation.map(([key, label]) => <Link key={key} className={section === key ? 'active' : ''} to={`/school/communication/${key}`}>{label}</Link>)}</nav>
    {error && <p className="form-error" role="alert">{error}</p>}{notice && <p className="communication-notice">{notice}</p>}
    {section === 'announcements' && <><section className="profile-section"><h2>Create announcement</h2><form className="student-form communication-form" onSubmit={saveDraft}><label>Title<input required name="title" value={form.title} onChange={setField} /></label><label>Message<textarea required name="message" value={form.message} onChange={setField} /></label><label>Audience<select name="audience" value={form.audience} onChange={setField}><option value="all_parents">All Parents</option><option value="class">Specific Class</option><option value="student">Specific Student</option><option value="parent">Specific Parent</option></select></label>{form.audience === 'class' && <label>Class<select required name="school_class" value={form.school_class} onChange={setField}><option value="">Choose a class</option>{classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}{form.audience === 'student' && <StudentPicker selected={selectedAnnouncementStudent} onChange={(student) => { setSelectedAnnouncementStudent(student); setForm((current) => ({ ...current, student: student ? String(student.id) : '' })) }} required />}{form.audience === 'parent' && <label>Parent<select required name="parent" value={form.parent} onChange={setField}><option value="">Choose a parent</option>{parents.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}</select></label>}<div className="channel-options"><label className="checkbox-label"><input type="checkbox" checked={form.channels.includes('in_app')} onChange={() => toggleChannel('in_app')} /> In-app notification</label><label className="checkbox-label"><input type="checkbox" checked={form.channels.includes('whatsapp')} onChange={() => toggleChannel('whatsapp')} /> WhatsApp (eligible opt-ins only)</label></div><button disabled={!form.channels.length} type="submit">Save draft and preview recipients</button></form>{draft && <div className="communication-confirm"><strong>Ready to send to {draft.recipient_count} parent{draft.recipient_count === 1 ? '' : 's'}?</strong><button onClick={confirmSend}>Confirm and send</button></div>}</section><section className="profile-section"><h2>Announcement history</h2><HistoryTable rows={announcements} /></section></>}
    {section === 'fee-reminders' && <section className="profile-section"><h2>Fee reminders</h2><p className="muted-copy">MTM calculates outstanding balances and eligible recipients before creating local notifications and WhatsApp outbox jobs.</p><button onClick={generateReminders}>Generate reminders for eligible accounts</button></section>}
    {section === 'history' && <section className="profile-section"><h2>Communication history</h2><HistoryTable rows={history} detailed /></section>}
    {section === 'settings' && settings && <section className="profile-section"><h2>WhatsApp and notification settings</h2><p className="muted-copy">WhatsApp integration: {settings.integration_available ? 'Server integration credential configured' : 'Not configured'}. No provider credentials are shown here.</p><form className="student-form communication-form" onSubmit={saveSettings}>{[['whatsapp_enabled', 'Enable WhatsApp communication'], ['payment_receipt_notifications_enabled', 'Payment receipt notifications'], ['fee_reminders_enabled', 'Fee reminder notifications'], ['report_card_notifications_enabled', 'Report-card notifications'], ['whatsapp_announcements_enabled', 'WhatsApp announcements']].map(([key, label]) => <label key={key} className="checkbox-label"><input type="checkbox" checked={settings[key]} onChange={(event) => setSettings((current) => ({ ...current, [key]: event.target.checked }))} /> {label}</label>)}<button type="submit">Save settings</button></form></section>}
  </main>
}

function HistoryTable({ rows, detailed = false }) {
  if (!rows.length) return <p className="muted-copy">No communication records are available.</p>
  return <div className="student-table-wrap"><table className="student-table"><thead><tr><th>Date</th><th>{detailed ? 'Recipient' : 'Audience'}</th>{detailed && <th>Student</th>}<th>Type</th>{detailed && <><th>Channel</th><th>Status</th></>}</tr></thead><tbody>{rows.map((item) => <tr key={item.id}><td>{new Date(item.created_at).toLocaleString()}</td><td>{detailed ? (item.parent_name || 'Parent') : `${item.audience.replace('_', ' ')}`}</td>{detailed && <td>{item.student_name || '—'}</td>}<td>{detailed ? item.description : item.title}</td>{detailed && <><td>{item.channel}</td><td>{item.status}{item.failure_reason ? ` — ${item.failure_reason}` : ''}</td></>}</tr>)}</tbody></table></div>
}
