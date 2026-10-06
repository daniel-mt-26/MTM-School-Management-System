import { useEffect, useState } from 'react'
import { getAcademicRecords, saveAcademicRecord } from '../api/academics'
export default function SubjectPicker({ value, onChange, subjects = [], required = false, disabled = false }) {
  const [groups, setGroups] = useState([])
  const [extra, setExtra] = useState([])
  const [search, setSearch] = useState('')
  const [custom, setCustom] = useState(false)
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { getAcademicRecords('subjects/library').then((data) => setGroups(data.groups)).catch(() => setError('Built-in subjects are unavailable. Existing subjects remain selectable.')) }, [])
  const all = [...subjects, ...extra.filter((x) => !subjects.some((s) => s.id === x.id))]
  async function choose(key) {
    if (key === 'custom') { setCustom(true); return }
    if (!key.startsWith('ZW-')) { onChange(key ? Number(key) : ''); return }
    setBusy(true); setError('')
    try { const [item] = await saveAcademicRecord('subjects/activate', { keys: [key] }); setExtra((old) => [...old.filter((x) => x.id !== item.id), item]); onChange(item.id) } catch { setError('Subject could not be selected. Connect and try again.') } finally { setBusy(false) }
  }
  async function addCustom() {
    setBusy(true); setError('')
    try { const item = await saveAcademicRecord('subjects', { name: name.trim(), code: `CUSTOM-${crypto.randomUUID().slice(0, 16)}`, is_active: true }); setExtra((old) => [...old, item]); onChange(item.id); setCustom(false); setName('') } catch { setError('Custom subject could not be saved. Check whether it already exists.') } finally { setBusy(false) }
  }
  return <div><label>Search subjects<input value={search} onChange={(e) => setSearch(e.target.value)} disabled={disabled} /></label><label>Subject<select required={required} disabled={disabled || busy} value={value || ''} onChange={(e) => choose(e.target.value)}><option value="">Choose subject</option><optgroup label="School subjects">{all.filter((x) => String(x.id) === String(value) || x.is_active && x.name.toLowerCase().includes(search.toLowerCase())).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</optgroup>{groups.map((group) => <optgroup key={group.name} label={group.name}>{group.subjects.filter((x) => x.name.toLowerCase().includes(search.toLowerCase()) && !all.some((s) => s.name.toLowerCase() === x.name.toLowerCase())).map((x) => <option key={x.key} value={x.key}>{x.name}</option>)}</optgroup>)}<option value="custom">Other / Custom Subject</option></select></label>{custom && <div><label>Custom subject name<input maxLength="100" value={name} onChange={(e) => setName(e.target.value)} /></label><button type="button" disabled={busy || !name.trim()} onClick={addCustom}>Add custom subject</button><button type="button" onClick={() => setCustom(false)}>Cancel</button></div>}{error && <p role="alert">{error}</p>}</div>
}
