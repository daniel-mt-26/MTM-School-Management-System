import { useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { getAcademicRecords } from '../api/academics'
import { getAttendanceRoster, saveAttendanceBulk } from '../api/attendance'
import { OfflineContext } from '../offline/context'
import { AttendanceClassList, AttendanceRoster } from '../components/AttendanceControls'
import { cacheAttendanceLookups, cachedAttendanceLookups, cachedAttendanceRoster, cacheAttendanceRoster, queueAttendanceBulk, attendanceWithLocalChanges } from '../offline/attendance'
import { discardOperation, syncMetadata, updateOperation } from '../offline/db'

const schoolDate = () => { const date = new Date(); return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}` }

export default function AttendancePage() {
  const offline = useContext(OfflineContext)
  const { scope, isReachable, queue = [], refresh, syncNow, syncRevision } = offline ?? {}
  const [lookups, setLookups] = useState({ classes: [], years: [], terms: [] })
  const [context, setContext] = useState({ school_class: '', academic_year: '', term: '', attendance_date: schoolDate() })
  const requestVersion = useRef(0)
  const selectionVersion = useRef(0)
  const [roster, setRoster] = useState(null)
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const issues = queue.filter((operation) => operation.module === 'attendance' && operation.status === 'failed')
  const terms = useMemo(() => lookups.terms.filter((term) => !context.academic_year || String(term.academic_year) === String(context.academic_year)), [lookups.terms, context.academic_year])
  const completeContext = context.school_class && context.academic_year && context.term && context.attendance_date

  useEffect(() => {
    if (!scope) return
    let active = true
    async function setup() {
      let data
      if (isReachable) {
        try {
          const [classes, years, terms] = await Promise.all([getAcademicRecords('classes'), getAcademicRecords('academic-years'), getAcademicRecords('terms')])
          data = { classes, years, terms }
          await cacheAttendanceLookups(scope, data)
        } catch { data = await cachedAttendanceLookups(scope) }
      } else data = await cachedAttendanceLookups(scope)
      if (!active) return
      if (!data) { setLoading(false); setError('No attendance class list is cached. Connect to load your school classes.'); return }
      setLookups(data)
      const current = data.years.find((year) => year.is_current) || data.years[0]
      const todayTerm = data.terms.find((term) => String(term.academic_year) === String(current?.id) && term.start_date <= schoolDate() && term.end_date >= schoolDate())
      setContext((value) => ({ ...value, academic_year: value.academic_year || String(current?.id || ''), term: value.term || String(todayTerm?.id || '') }))
    }
    setup().catch(() => active && setError('Attendance setup could not be loaded.'))
    return () => { active = false }
  }, [isReachable, scope])

  async function selectClass(id) {
    const selection = ++selectionVersion.current
    requestVersion.current++
    setRoster(null); setError(''); setNotice('')
    if (!isReachable && id) {
      const metadata = await syncMetadata(scope)
      if (selection !== selectionVersion.current) return
      const saved = (metadata.attendanceContexts || []).filter((x) => String(x.school_class) === id).at(-1)
      if (saved) {
        setContext({ school_class: id, academic_year: String(saved.academic_year), term: String(saved.term), attendance_date: saved.attendance_date })
        setNotice('Showing the most recently cached date for this class. Check the date before saving.')
      } else { setContext((old) => ({ ...old, school_class: id })); setError('This class has no cached roster. Connect and open its roster first.') }
    } else setContext((old) => ({ ...old, school_class: id }))
  }

  const load = useCallback(async () => {
    const version = ++requestVersion.current
    const applyRoster = (value) => { if (version === requestVersion.current) setRoster(value) }
    if (!scope || !completeContext) { setLoading(false); return }
    setLoading(true); setError('')
    try {
      if (isReachable) {
        const server = await getAttendanceRoster(context)
        applyRoster(await attendanceWithLocalChanges(scope, await cacheAttendanceRoster(scope, server)))
      } else {
        const cached = await cachedAttendanceRoster(scope, context)
        applyRoster(await attendanceWithLocalChanges(scope, cached))
        if (!cached && version === requestVersion.current) setError('This roster has not been synchronized on this device yet.')
      }
    } catch {
      const cached = await cachedAttendanceRoster(scope, context)
      applyRoster(await attendanceWithLocalChanges(scope, cached))
      if (!cached && version === requestVersion.current) setError('Attendance roster could not be loaded.')
    } finally { if (version === requestVersion.current) setLoading(false) }
  }, [completeContext, context, isReachable, scope])
  const invalidateRoster = useCallback(() => { requestVersion.current++ }, [])
  useEffect(() => { const timer = window.setTimeout(() => { void load() }, 0); return () => { invalidateRoster(); window.clearTimeout(timer) } }, [load, syncRevision, invalidateRoster])

  const setContextField = (field, value) => { requestVersion.current++; setRoster(null); setContext((current) => ({ ...current, [field]: value, ...(field === 'academic_year' ? { term: '' } : {}) })) }
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
    {!context.school_class && <AttendanceClassList classes={lookups.classes} offline={!isReachable} onSelect={selectClass} />}
    {context.school_class && <><button type="button" onClick={() => selectClass('')}>Back to class list</button><h2>{lookups.classes.find((x) => String(x.id) === context.school_class)?.name}</h2><section className="academic-filters attendance-filters"><label>Academic Year<select value={context.academic_year} onChange={(event) => setContextField('academic_year', event.target.value)}><option value="">Choose year</option>{lookups.years.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Term<select value={context.term} onChange={(event) => setContextField('term', event.target.value)}><option value="">Choose term</option>{terms.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Date<input type="date" value={context.attendance_date} onChange={(event) => setContextField('attendance_date', event.target.value)} /></label></section></>}
    {roster && !isReachable && <p className="inventory-cache-notice">Offline — roster last synced: {new Date(roster.cachedAt).toLocaleString()}. {roster.hasLocalChanges && 'Pending attendance is included.'}</p>}
    {error && <p className="form-error">{error}</p>}{notice && <p className="communication-notice">{notice}</p>}
    {issues.length > 0 && <section className="inventory-sync-issues"><h2>{issues[0].failureCategory === 'conflict' ? 'Attendance conflict' : 'Attendance sync issue'}</h2>{issues.map((operation) => <div key={operation.id}><strong>{operation.payload.attendance_date}</strong><p>{operation.failureMessage || 'Review this attendance submission before retrying.'}</p><button type="button" className="inline-button" onClick={() => retry(operation)}>Retry</button><button type="button" className="text-button" onClick={() => discardToServer(operation)}>Use server value</button></div>)}</section>}
    {context.school_class && (loading ? <div className="student-state">Loading attendance...</div> : roster && <AttendanceRoster roster={roster} onMark={mark} onMarkAll={markAllPresent} onSave={save} />)}
  </main>
}
