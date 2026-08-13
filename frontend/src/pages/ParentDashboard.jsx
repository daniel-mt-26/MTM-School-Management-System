import { useEffect, useMemo, useState } from 'react'
import { apiClient } from '../api/client'

const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']

export default function ParentDashboard() {
  const [students, setStudents] = useState([])
  const [selected, setSelected] = useState('')
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => { apiClient('/parent/students/').then((items) => { setStudents(items); setSelected(items[0]?.id ? String(items[0].id) : '') }).catch(() => setError('We could not load your linked children.')).finally(() => setLoading(false)) }, [])
  useEffect(() => { if (selected) apiClient(`/parent/students/${selected}/timetable/`).then(setEntries).catch(() => setError('We could not load this class timetable.')) }, [selected])
  const slots = useMemo(() => Array.from(new Set(entries.map((entry) => `${entry.start_time} – ${entry.end_time}`))).sort(), [entries])
  const entryAt = (slot, day) => entries.find((entry) => `${entry.start_time} – ${entry.end_time}` === slot && entry.day_of_week === day)
  if (loading) return <main className="school-profile-state">Loading your children…</main>
  return <main className="student-page"><header className="student-page-header"><div><h1>Parent Portal</h1><p>Read-only class timetables for your linked children.</p></div></header>{error && <p className="form-error">{error}</p>}
    {students.length ? <><section className="profile-section"><label className="timetable-selector">Child<select value={selected} onChange={(event) => setSelected(event.target.value)}>{students.map((student) => <option key={student.id} value={student.id}>{student.display_name} · {student.class_name}</option>)}</select></label></section><div className="student-table-wrap timetable-grid"><table className="student-table"><thead><tr><th>Time</th>{days.map((day) => <th key={day}>{day}</th>)}</tr></thead><tbody>{slots.length ? slots.map((slot) => <tr key={slot}><th>{slot}</th>{days.map((day) => <td key={day}>{entryAt(slot, day)?.display_label || ''}</td>)}</tr>) : <tr><td colSpan="6" className="empty-cell">No timetable entries are available for this child&apos;s current class.</td></tr>}</tbody></table></div></> : <div className="student-state">No children are currently linked to this account.</div>}</main>
}
