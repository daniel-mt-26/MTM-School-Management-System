import { useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { getAcademicRecords } from '../api/academics'
import { getAttendanceRoster, saveAttendanceBulk } from '../api/attendance'
import { OfflineContext } from '../offline/context'
import { cachedAttendanceRoster, cacheAttendanceRoster, queueAttendanceBulk, attendanceWithLocalChanges } from '../offline/attendance'
import { discardOperation, syncMetadata, updateOperation } from '../offline/db'

const statuses = [['present', 'Present'], ['absent', 'Absent'], ['late', 'Late'], ['excused', 'Excused']]
const schoolDate = () => { const date = new Date(); return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}` }

export default function AttendancePage() {
  const offline = useContext(OfflineContext)
  const { scope, isReachable, queue = [], refresh, syncNow, syncRevision } = offline ?? {}
  const [lookups, setLookups] = useState({ classes: [], years: [], terms: [] })
  const [context, setContext] = useState({ school_class: '', academic_year: '', term: '', attendance_date: schoolDate() })
  const [roster, setRoster] = useState(null)
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const issues = queue.filter((operation) => operation.module === 'attendance' && operation.status === 'failed')
  const terms = useMemo(() => lookups.terms.filter((term) => !context.academic_year || String(term.academic_year) === String(context.academic_year)), [lookups.terms, context.academic_year])
  const completeContext = context.school_class && context.academic_year && context.term && context.attendance_date

  useEffect(() => {
    if (!scope || !isReachable) return
    Promise.all([getAcademicRecords('classes'), getAcademicRecords('academic-years'), getAcademicRecords('terms')]).then(([classes, years, terms]) => {
      setLookups({ classes, years, terms })
      const current = years.find((year) => year.is_current) || years[0]
      const firstTerm = terms.find((term) => String(term.academic_year) === String(current?.id))
      setContext((value) => ({ ...value, school_class: value.school_class || String(classes.find((item) => item.is_active)?.id || ''), academic_year: value.academic_year || String(current?.id || ''), term: value.term || String(firstTerm?.id || '') }))
    }).catch(() => setError('Attendance setup could not be loaded. Open a previously synchronized roster while offline.'))
  }, [isReachable, scope])
  useEffect(() => {
    if (!scope || isReachable) return
    syncMetadata(scope).then((metadata) => {
      const saved = metadata.attendanceContexts?.[metadata.attendanceContexts.length - 1]
      if (!saved) return
      setLookups({ classes: [{ id: saved.school_class, name: saved.class_name, is_active: true }], years: [{ id: saved.academic_year, name: saved.academic_year_name }], terms: [{ id: saved.term, name: saved.term_name, academic_year: saved.academic_year }] })
      setContext({ school_class: String(saved.school_class), academic_year: String(saved.academic_year), term: String(saved.term), attendance_date: saved.attendance_date })
    }).catch(() => {})
  }, [isReachable, scope])

  const load = useCallback(async () => {
    if (!scope || !completeContext) { setLoading(false); return }
    setLoading(true); setError('')
    try {
      if (isReachable) {
        const server = await getAttendanceRoster(context)
        setRoster(await attendanceWithLocalChanges(scope, await cacheAttendanceRoster(scope, server)))
      } else {
        const cached = await cachedAttendanceRoster(scope, context)
        setRoster(await attendanceWithLocalChanges(scope, cached))
        if (!cached) setError('This roster has not been synchronized on this device yet.')
      }
    } catch {
      const cached = await cachedAttendanceRoster(scope, context)
      setRoster(await attendanceWithLocalChanges(scope, cached))
      if (!cached) setError('Attendance roster could not be loaded.')
    } finally { setLoading(false) }
  }, [completeContext, context, isReachable, scope])
  useEffect(() => { const timer = window.setTimeout(() => { void load() }, 0); return () => window.clearTimeout(timer) }, [load, syncRevision])

  const setContextField = (field, value) => setContext((current) => ({ ...current, [field]: value, ...(field === 'academic_year' ? { term: '' } : {}) }))
  const mark = (enrollment, status) => setRoster((current) => current && ({ ...current, students: current.students.map((student) => student.enrollment === enrollment ? { ...student, attendance: { status, updated_at: student.attendance?.updated_at ?? null }, changed: true } : student) }))
  const markAllPresent = () => setRoster((current) => current && ({ ...current, students: current.students.map((student) => ({ ...student, attendance: { status: 'present', updated_at: student.attendance?.updated_at ?? null }, changed: true })) }))
  async function save() {
    if (!roster) return
    const payload = { school_class: Number(roster.school_class), academic_year: Number(roster.academic_year), term: Number(roster.term), attendance_date: roster.attendance_date, entries: roster.students.map((student) => ({ enrollment: student.enrollment, status: student.attendance?.status || 'present', last_known_updated_at: student.attendance?.updated_at || null })) }
    setError(''); setNotice('')
    try {
      if (!isReachable) { await queueAttendanceBulk(scope, payload); setRoster(await attendanceWithLocalChanges(scope, await cachedAttendanceRoster(scope, context))); await refresh?.(); setNotice('Attendance saved locally. It will synchronize when you reconnect.'); return }
      const result = await saveAttendanceBulk(payload, crypto.randomUUID())
      setRoster(await attendanceWithLocalChanges(scope, await cacheAttendanceRoster(scope, result.roster)))
      setNotice('Attendance saved.')
    } catch (caught) { setError(caught?.data?.detail || 'Attendance could not be saved.') }
  }
  async function retry(operation) { await updateOperation(operation.id, { status: 'pending', retryCount: 0, failureCategory: null, failureMessage: null }); await refresh?.(); if (isReachable) await syncNow(true) }
  async function discardToServer(operation) { await discardOperation(operation.id); await refresh?.(); await load(); setNotice('Local attendance change discarded. The server roster is now shown.') }

  return <main className="student-page"><header className="student-page-header"><div><Link to="/school/academics" className="dashboard-link">Back to Academics</Link><h1>Attendance</h1><p>Take daily class attendance, including when connectivity is unavailable.</p></div></header>
    <section className="academic-filters attendance-filters"><label>Class<select value={context.school_class} onChange={(event) => setContextField('school_class', event.target.value)}><option value="">Choose class</option>{lookups.classes.filter((item) => item.is_active).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Academic Year<select value={context.academic_year} onChange={(event) => setContextField('academic_year', event.target.value)}><option value="">Choose year</option>{lookups.years.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Term<select value={context.term} onChange={(event) => setContextField('term', event.target.value)}><option value="">Choose term</option>{terms.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Date<input type="date" value={context.attendance_date} onChange={(event) => setContextField('attendance_date', event.target.value)} /></label></section>
    {roster && !isReachable && <p className="inventory-cache-notice">Offline — roster last synced: {new Date(roster.cachedAt).toLocaleString()}. {roster.hasLocalChanges && 'Pending attendance is included.'}</p>}
    {error && <p className="form-error">{error}</p>}{notice && <p className="communication-notice">{notice}</p>}
    {issues.length > 0 && <section className="inventory-sync-issues"><h2>{issues[0].failureCategory === 'conflict' ? 'Attendance conflict' : 'Attendance sync issue'}</h2>{issues.map((operation) => <div key={operation.id}><strong>{operation.payload.attendance_date}</strong><p>{operation.failureMessage || 'Review this attendance submission before retrying.'}</p><button type="button" className="inline-button" onClick={() => retry(operation)}>Retry</button><button type="button" className="text-button" onClick={() => discardToServer(operation)}>Use server value</button></div>)}</section>}
    {loading ? <div className="student-state">Loading attendance…</div> : roster && <section className="profile-section attendance-roster"><div className="inventory-form-heading"><h2>{roster.class_name} · {roster.attendance_date}</h2><button type="button" className="secondary-button" onClick={markAllPresent}>Mark all Present</button></div><div className="student-table-wrap"><table className="student-table"><thead><tr><th>Student</th><th>Attendance</th><th>Sync</th></tr></thead><tbody>{roster.students.map((student) => <tr key={student.enrollment}><td><strong>{student.display_name}</strong><span className="table-subtext">{student.admission_number}</span></td><td><select value={student.attendance?.status || 'present'} onChange={(event) => mark(student.enrollment, event.target.value)}>{statuses.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></td><td>{student.syncStatus === 'failed' ? 'Sync issue' : student.syncStatus ? 'Pending sync' : 'Synced'}</td></tr>)}</tbody></table></div><button type="button" onClick={save}>Save Attendance</button></section>}
  </main>
}
