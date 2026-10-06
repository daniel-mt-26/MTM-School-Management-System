import SubjectPicker from './SubjectPicker'
import { emptyEntry } from './timetableDefaults.js'
const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

export default function TimetableEditor({ form, setForm, lookups, onSave, busy, error }) {
  const set = (key, value) => setForm((old) => ({ ...old, [key]: value, ...(key === 'academic_year' ? { term: '' } : {}) }))
  const rowSet = (index, changes) => setForm((old) => ({ ...old, entries: old.entries.map((row, i) => i === index ? { ...row, ...changes } : row) }))
  const select = (key, label, options) => <label>{label}<select required value={form[key]} onChange={(e) => set(key, e.target.value)}><option value="">Choose {label.toLowerCase()}</option>{options.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
  return <form className="student-form academic-form" onSubmit={onSave}><h2>{form.id ? 'Edit Timetable' : 'Create Timetable'}</h2>
    <label>Timetable Name<input required maxLength="150" value={form.name} onChange={(e) => set('name', e.target.value)} /></label>
    {select('academic_year', 'Academic Year', lookups.years)}{select('term', 'Term', lookups.terms.filter((x) => String(x.academic_year) === String(form.academic_year)))}
    {!lookups.years.length && <p>No academic years loaded. Create a year in Academics or retry loading this page.</p>}
    {form.academic_year && !lookups.terms.some((x) => String(x.academic_year) === String(form.academic_year)) && <p>No terms exist for this year.</p>}
    <label>Applies To<select value={form.scope || 'MULTIPLE'} onChange={(e) => setForm((old) => ({ ...old, scope: e.target.value, classes: [] }))}><option value="SINGLE">One Class</option><option value="MULTIPLE">Multiple Classes</option><option value="WHOLE_SCHOOL">Whole School</option></select></label>
    {form.scope === 'SINGLE' ? <label>Class<select required value={form.classes[0] || ''} onChange={(e) => set('classes', e.target.value ? [Number(e.target.value)] : [])}><option value="">Choose class</option>{lookups.classes.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label> : form.scope === 'WHOLE_SCHOOL' ? <p>Applies to all active school classes, including classes added later. Dates are determined by the selected year and term.</p> : <fieldset><legend>Applies to classes</legend>{lookups.classes.map((x) => <label key={x.id}><input type="checkbox" checked={form.classes.includes(x.id)} onChange={(e) => set('classes', e.target.checked ? [...form.classes, x.id] : form.classes.filter((id) => id !== x.id))} />{x.name}{!x.is_active && ' (inactive)'}</label>)}</fieldset>}
    {form.entries.map((row, index) => <fieldset key={row.id || `new-${index}`}><legend>Entry {index + 1}</legend><label>Day<select value={row.day_of_week} onChange={(e) => rowSet(index, { day_of_week: e.target.value })}>{days.map((day) => <option key={day}>{day}</option>)}</select></label>
      <label>Start Time<input required type="time" value={row.start_time} onChange={(e) => rowSet(index, { start_time: e.target.value })} /></label><label>End Time<input required type="time" value={row.end_time} onChange={(e) => rowSet(index, { end_time: e.target.value })} /></label>
      <label>Entry Type<select value={row.subject !== null ? 'subject' : 'activity'} onChange={(e) => rowSet(index, e.target.value === 'subject' ? { subject: '', label: '' } : { subject: null, label: 'Assembly' })}><option value="subject">Subject</option><option value="activity">Activity</option></select></label>
      {row.subject !== null ? <SubjectPicker required value={row.subject} subjects={lookups.subjects} onChange={(value) => rowSet(index, { subject: value, label: '' })} /> : <label>Activity<select value={row.label} onChange={(e) => rowSet(index, { label: e.target.value })}>{Array.from(new Set([...lookups.activities, row.label].filter(Boolean))).map((name) => <option key={name}>{name}</option>)}</select></label>}
      <button type="button" onClick={() => set('entries', form.entries.filter((_, i) => i !== index))}>Remove entry {index + 1}</button>
    </fieldset>)}
    <button type="button" onClick={() => set('entries', [...form.entries, emptyEntry()])}>Add entry</button>
    {error && <p role="alert" className="form-error">{error}</p>}
    <button disabled={busy || (form.scope !== 'WHOLE_SCHOOL' && !form.classes.length) || !form.entries.length}>Save Timetable</button>
  </form>
}
