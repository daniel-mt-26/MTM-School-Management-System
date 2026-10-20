import { useEffect, useState } from 'react'
import { apiClient, apiDownload } from '../api/client'
import SortableTable from './SortableTable.jsx'

export default function AttendanceRegister({ lookups }) {
  const now = new Date()
  const [filters, setFilters] = useState({ academic_year: '', term: '', school_class: '', month: now.getMonth() + 1, calendar_year: now.getFullYear() })
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const complete = filters.academic_year && filters.term && filters.school_class
  const query = new URLSearchParams(filters).toString()
  useEffect(() => {
    if (!complete) return
    let active = true
    apiClient(`/school/attendance/register/?${query}`).then(value => { if (active) { setData(value); setError('') } }).catch(() => { if (active) { setData(null); setError('Could not load this register. Connect and check your filters.') } })
    return () => { active = false }
  }, [query, complete])
  const change = (key, value) => { setData(null); setFilters(old => ({ ...old, [key]: value, ...(key === 'academic_year' ? { term: '' } : {}) })) }
  const download = async kind => { try { await apiDownload(`/school/attendance/register/?${query}&export=${kind}`, `attendance-register.${kind}`) } catch { setError('Export failed. Please try again.') } }
  return <section className="attendance-register"><h2>Monthly Attendance Register</h2><div className="academic-filters">{[['academic_year', 'Academic Year', lookups.years], ['term', 'Term', lookups.terms.filter(t => String(t.academic_year) === String(filters.academic_year))], ['school_class', 'Class', lookups.classes]].map(([key, label, options]) => <label key={key}>{label}<select value={filters[key]} onChange={e => change(key, e.target.value)}><option value="">Select</option>{options.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>)}<label>Calendar Year<input type="number" min="1900" max="9999" value={filters.calendar_year} onChange={e => change('calendar_year', e.target.value)} /></label><label>Month<select value={filters.month} onChange={e => change('month', e.target.value)}>{Array.from({ length: 12 }, (_, i) => <option key={i} value={i + 1}>{new Date(2000, i, 1).toLocaleString(undefined, { month: 'long' })}</option>)}</select></label></div>{error && <p role="alert">{error}</p>}{data && <><div className="register-actions"><button onClick={() => window.print()}>Print Register</button><button onClick={() => download('pdf')}>Export PDF</button><button onClick={() => download('xlsx')}>Export Excel</button></div><h3>{data.school} · {data.school_class}</h3><p>{data.academic_year} · {data.term} · {data.month}</p><p>Teachers: {data.teachers.map(t => t.join(' ')).join(', ') || 'Unassigned'} · Generated {new Date(data.generated_at).toLocaleString()}</p><p>P = Present · A = Absent · L = Late · E = Excused. Attendance % = (Present + Late) / marked days.</p><div className="register-scroll"><SortableTable className="student-table"><thead><tr><th>No.</th><th>Student Name</th><th>Admission Number</th>{data.days.map(day => <th key={day}>{day}</th>)}<th>Present</th><th>Absent</th><th>Late</th><th>Excused</th><th>Attendance %</th></tr></thead><tbody>{data.rows.map((row, index) => <tr key={row.id}><td>{index + 1}</td><td>{row.student_name}</td><td>{row.admission_number}</td>{row.days.map((code, i) => <td className={`attendance-code code-${code}`} key={i}>{code || '—'}</td>)}<td>{row.present}</td><td>{row.absent}</td><td>{row.late}</td><td>{row.excused}</td><td>{row.percentage == null ? '—' : `${row.percentage}%`}</td></tr>)}</tbody></SortableTable></div></>}</section>
}
