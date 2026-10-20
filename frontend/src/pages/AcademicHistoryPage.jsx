import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { apiClient, apiDownload } from '../api/client'
import SchoolLetterhead from '../components/SchoolLetterhead'
import StudentPicker from '../components/StudentPicker'

export default function AcademicHistoryPage({ parent = false, teacher = false }) {
  const { studentId } = useParams()
  const [student, setStudent] = useState(null), [data, setData] = useState(null), [error, setError] = useState('')
  const [filters, setFilters] = useState({ academic_year: '', term: '' })
  const role = parent ? 'parent' : teacher ? 'teacher' : 'school'
  const id = studentId || student?.id
  const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value)).toString()
  const path = `/${role}/students/${id}/academic-history/`
  useEffect(() => { if (!id) return; let active = true; apiClient(`${path}?${query}`).then(value => { if (active) { setData(value); setError('') } }).catch(() => { if (active) { setData(null); setError('Published academic history could not be loaded.') } }); return () => { active = false } }, [id, path, query])
  const terms = data?.terms ? data.terms.filter(t => !filters.academic_year || String(t.academic_year) === filters.academic_year) : [...new Map((data?.periods || []).filter(p => !filters.academic_year || String(p.academic_year_id) === filters.academic_year).map(p => [p.term_id, { id: p.term_id, name: p.term }])).values()]
  async function download() { try { await apiDownload(`${path}?${query}&export=pdf`, `academic-history-${id}.pdf`) } catch { setError('The academic record export failed.') } }
  return <main className="student-page account-statement"><div className="statement-controls"><Link to={parent ? '/parent' : teacher ? '/teacher/students' : '/school/academics'}>Back to {parent ? 'Parent Portal' : teacher ? 'Students' : 'Academics'}</Link><h1>Historical Academic Record</h1>{!studentId && !parent && !teacher && <StudentPicker selected={student} onChange={value => { setStudent(value); setData(null); setFilters({ academic_year: '', term: '' }) }} />}{data && <div className="academic-filters">{[['academic_year', 'Academic Year', data.years], ['term', 'Term', terms]].map(([key, label, options]) => <label key={key}>{label}<select value={filters[key]} onChange={e => setFilters(old => ({ ...old, [key]: e.target.value, ...(key === 'academic_year' ? { term: '' } : {}) }))}><option value="">All</option>{options.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>)}<button onClick={download}>Download PDF</button><button onClick={() => window.print()}>Print Academic Record</button></div>}</div>
    {error && <p role="alert">{error}</p>}{data && <article className="statement-document"><SchoolLetterhead school={data.school} /><h2>{data.student.name}</h2><p>Admission Number: {data.student.admission_number}</p><p>{data.note}</p>{data.periods.map(period => <section key={period.report_card} className="academic-history-period"><h2>{period.academic_year} / {period.term}</h2><p>Class / Grade: {period.class_name} · Publication version: {period.version || 'Legacy'}</p><table className="student-table"><thead><tr>{['Subject', 'Mark', 'Maximum', 'Percentage', 'Official Grade', 'Published Comment'].map(x => <th key={x}>{x}</th>)}</tr></thead><tbody>{period.results.map(result => <tr key={result.id}><td>{result.subject}</td><td>{result.score}</td><td>{result.maximum_score}</td><td>{result.percentage}%</td><td>{result.grade || '—'}</td><td>{result.comment}</td></tr>)}</tbody></table>{period.comments.map((comment, i) => <p key={i}>{comment}</p>)}</section>)}{!data.periods.length && <p>No published academic records are available for this selection.</p>}</article>}</main>
}
