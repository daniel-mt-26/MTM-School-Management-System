import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiClient } from '../api/client'
import { getFinanceRecords, saveFinanceRecord } from '../api/finance'
import FeeRecordActions from '../components/FeeRecordActions'
import StudentPicker from '../components/StudentPicker'

const blank = { billing_method: 'MONTHLY', name: '', amount: '', academic_year: '', term: '', school_class: null, student: null, is_active: true }
const errorText = (e) => Object.values(e.data || {}).flat().join(' ') || e.message || 'Request failed.'
export default function FeeManagementPage() {
  const [tab, setTab] = useState('Fee Structures')
  const [form, setForm] = useState(blank)
  const [scope, setScope] = useState('school')
  const [student, setStudent] = useState(null)
  const [data, setData] = useState({ structures: [], fees: [], years: [], terms: [], classes: [], charges: [] })
  const [preview, setPreview] = useState(null)
  const [selected, setSelected] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  async function load() {
    const [structures, years, terms, classes, charges, fees] = await Promise.all(['recurring-fees', 'academic-years', 'terms', 'classes', 'fee-assignments', 'fees'].map((resource) => getFinanceRecords(resource)))
    setData({ structures, years, terms, classes, charges, fees })
  }
  useEffect(() => { Promise.resolve().then(load).catch((e) => setError(errorText(e))) }, [])
  const set = (key, value) => { setForm((old) => ({ ...old, [key]: value, ...(key === 'academic_year' ? { term: '' } : {}) })); setPreview(null) }
  const term = data.terms.find((x) => String(x.id) === String(form.term))
  async function run(action) { setBusy(true); setError(''); try { await action() } catch (e) { setError(errorText(e)); setPreview(null) } finally { setBusy(false) } }
  async function previewFee(id) { setPreview(await apiClient(`/school/recurring-fees/${id}/preview/`)); setSelected(String(id)); setTab('Generate Charges') }
  async function save(event) {
    event.preventDefault()
    await run(async () => {
      const item = await saveFinanceRecord('recurring-fees', form)
      setNotice('Fee structure saved. No charges have been created.'); setForm(blank); setStudent(null); setScope('school'); await load()
      if (item.is_active) await previewFee(item.id)
    })
  }
  const pick = (key, label, options) => <label>{label}<select required value={form[key] || ''} onChange={(e) => set(key, e.target.value)}><option value="">Choose {label.toLowerCase()}</option>{options.map((x) => <option value={x.id} key={x.id}>{x.name}</option>)}</select></label>
  return <main className="student-page"><header className="student-page-header"><div><Link to="/school/finance">Back to Finance</Link><h1>Fee Management</h1><p>Define fees, select scope, preview obligations and confirm charges.</p></div></header>
    <nav className="academic-filters">{['Fee Structures', 'Assignments / Scope', 'Generate Charges', 'Existing Charges'].map((name) => <button type="button" key={name} onClick={() => setTab(name)} aria-pressed={tab === name}>{name}</button>)}</nav>
    {error && <p role="alert" className="form-error">{error}</p>}{notice && <p role="status">{notice}</p>}
    {tab === 'Fee Structures' && <><form className="student-form academic-form" onSubmit={save}><h2>Create Fee</h2>
      <label>Billing Method<select value={form.billing_method} onChange={(e) => set('billing_method', e.target.value)}><option value="MONTHLY">Monthly</option><option value="TERMLY">Termly</option><option value="ONE_OFF">One-off</option></select></label>
      <label>Fee Name<input required maxLength="150" value={form.name} onChange={(e) => set('name', e.target.value)} /></label>
      <label>{form.billing_method === 'MONTHLY' ? 'Monthly Amount' : form.billing_method === 'TERMLY' ? 'Term Amount' : 'Amount'}<input required type="number" min="0.01" step="0.01" value={form.amount} onChange={(e) => set('amount', e.target.value)} /></label><p>Uses the school’s operational currency.</p>
      <h3>Academic Context</h3>{pick('academic_year', 'Academic Year', data.years)}{pick('term', 'Term', data.terms.filter((x) => String(x.academic_year) === String(form.academic_year)))}
      {term && <p>Term dates: {term.start_date} – {term.end_date}. {form.billing_method === 'MONTHLY' ? `${term.billable_months} billable months ? ${(Number(form.amount || 0) * term.billable_months).toFixed(2)} per fully enrolled learner.` : 'One charge per eligible learner.'}</p>}
      <h3>Scope</h3><label>Scope<select value={scope} onChange={(e) => { setScope(e.target.value); setForm((old) => ({ ...old, school_class: null, student: null })); setStudent(null) }}><option value="school">School-wide</option><option value="class">Class / Grade</option><option value="student">Individual learner</option></select></label>
      {scope === 'class' && pick('school_class', 'Class / Grade', data.classes)}
      {scope === 'student' && <StudentPicker required selected={student} onChange={(value) => { setStudent(value); set('student', value?.id || null) }} />}
      <label><input type="checkbox" checked={form.is_active} onChange={(e) => set('is_active', e.target.checked)} /> Active</label>
      <button disabled={busy || (scope === 'student' && !student)}>Save and preview</button>
    </form><h2>Fee Structures</h2><p>Deactivate keeps the record and stops future use or generation. Delete permanently removes only an unused mistaken setup record and cannot be undone.</p>{data.structures.map((x) => <section className="profile-section" key={x.id}><h3>{x.name}</h3><p>{x.billing_method} · {x.currency} {x.amount} · {x.is_active ? 'Active' : 'Inactive'}</p><FeeRecordActions record={x} recurring onDelete={(id) => apiClient(`/school/recurring-fees/${id}/`, { method: 'DELETE' })} onDeleted={(id) => { setData((old) => ({ ...old, structures: old.structures.filter((item) => item.id !== id) })); setPreview(null); setSelected(''); setNotice('Recurring fee permanently deleted.') }} onDeactivate={async (id, is_active) => { await saveFinanceRecord('recurring-fees', { is_active }, id); setPreview(null); await load() }} />{x.billing_method !== 'LEGACY' && x.is_active && <button disabled={busy} onClick={() => run(() => previewFee(x.id))}>Preview charges</button>}{x.billing_method === 'LEGACY' && <Link to="/school/finance/recurring-fees">Manage legacy monthly schedule</Link>}</section>)}<h2>Existing Fees</h2>{data.fees.map((x) => <section className="profile-section" key={x.id}><h3>{x.name}</h3><p>{x.currency} {x.amount} ? {x.academic_year_name} / {x.term_name}</p><FeeRecordActions record={x} onDelete={(id) => apiClient(`/school/fees/${id}/`, { method: 'DELETE' })} onDeleted={(id) => { setData((old) => ({ ...old, fees: old.fees.filter((item) => item.id !== id) })); setNotice('Fee permanently deleted.') }} onDeactivate={async (id, is_active) => { await saveFinanceRecord('fees', { is_active }, id); await load() }} /></section>)}<Link to="/school/finance/fees">Manage existing fee definitions</Link></>}
    {tab === 'Assignments / Scope' && <><p>Scope is chosen when creating a fee. Eligibility uses enrollment history for the selected academic year and period, including historical class membership.</p>{data.structures.map((x) => <p key={x.id}>{x.name}: {x.student ? `Individual learner #${x.student}` : x.class_name || 'School-wide'}</p>)}<Link to="/school/finance/assignments">Manage existing individual assignments</Link></>}
    {tab === 'Generate Charges' && <section className="student-form"><label>Fee Structure<select value={selected} onChange={(e) => { setSelected(e.target.value); setPreview(null) }}><option value="">Choose a fee</option>{data.structures.filter((x) => x.is_active && x.billing_method !== 'LEGACY').map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label><button disabled={busy || !selected} onClick={() => run(() => previewFee(selected))}>Preview</button>
      {preview && <><h2>{preview.name}</h2><p>{preview.academic_year} / {preview.term} · {preview.term_start} – {preview.term_end}</p><p>{preview.billing_method} · {preview.currency} {preview.amount} per period</p><p>{preview.charges_per_student} {preview.billing_method === 'MONTHLY' ? 'billable months' : 'charge'} per fully enrolled learner · {preview.currency} {preview.amount_per_student} full obligation</p><p>Eligible learners: {preview.eligible_students}. Charges to create: {preview.total_charges}. Total value: {preview.currency} {preview.total_value}.</p><p>Learners enrolled for only part of the term are charged only for overlapping periods. Existing charges are excluded from the new total.</p>{preview.periods.map((p) => <p key={p.sequence}>Period {p.sequence}: {p.start} – {p.end}, {p.charges_to_create} new charges</p>)}{preview.missing_enrollments.length > 0 && <details><summary>{preview.missing_enrollments.length} learners lack enrollment records for this year</summary>{preview.missing_enrollments.map((s) => <p key={s.id}>{s.admission_number} · {s.first_name} {s.last_name}</p>)}</details>}<button disabled={busy || !preview.total_charges} onClick={() => run(async () => { const result = await apiClient(`/school/recurring-fees/${selected}/generate-charges/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ confirm: true, preview_token: preview.preview_token }) }); setNotice(`${result.assignments_created} charges created.`); setPreview(null); await load() })}>Confirm and generate {preview.total_charges} charges</button></>}
    </section>}
    {tab === 'Existing Charges' && <div className="student-table-wrap"><table className="student-table"><thead><tr>{['Fee / Period', 'Academic Year', 'Term', 'Student', 'Amount'].map((x) => <th key={x}>{x}</th>)}</tr></thead><tbody>{data.charges.map((x) => <tr key={x.id}><td>{x.fee_name}</td><td>{x.academic_year_name}</td><td>{x.term_name}</td><td><Link to={`/school/finance/students/${x.student}`}>{x.student_name}</Link></td><td>{x.currency} {x.amount_owed}</td></tr>)}</tbody></table></div>}
  </main>
}
