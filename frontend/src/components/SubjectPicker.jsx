import { useEffect, useId, useRef, useState } from 'react'
import { getAcademicRecords, saveAcademicRecord } from '../api/academics'

export default function SubjectPicker({ value, onChange, subjects = [], required = false, disabled = false }) {
  const id = useId()
  const input = useRef(null)
  const [groups, setGroups] = useState([])
  const [extra, setExtra] = useState([])
  const [query, setQuery] = useState(null)
  const [open, setOpen] = useState(false)
  const [highlight, setHighlight] = useState(0)
  const [custom, setCustom] = useState(false)
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let active = true
    getAcademicRecords('subjects/library').then((data) => { if (active) setGroups(data.groups) }).catch(() => { if (active) setError('Built-in subjects are unavailable. Existing subjects remain selectable.') })
    return () => { active = false }
  }, [])
  const all = [...subjects, ...extra.filter((x) => !subjects.some((s) => s.id === x.id))]
  const selected = all.find((item) => String(item.id) === String(value))
  const choices = all.filter((x) => x.is_active || String(x.id) === String(value)).map((x) => ({ key: String(x.id), name: x.name, group: 'School subjects' }))
  const seen = new Set(choices.map((x) => x.name.toLowerCase()))
  for (const group of groups) for (const subject of group.subjects) {
    if (!seen.has(subject.name.toLowerCase())) { choices.push({ ...subject, group: group.name }); seen.add(subject.name.toLowerCase()) }
  }
  const matches = choices.filter((item) => item.name.toLowerCase().includes((query || '').trim().toLowerCase()))
  const options = [...matches, { key: 'custom', name: 'Other / Custom Subject', group: '' }]
  const activeIndex = Math.min(highlight, options.length - 1)
  const text = query ?? selected?.name ?? ''
  useEffect(() => {
    input.current?.setCustomValidity(busy ? 'Wait for subject selection to finish.' : text && !value ? 'Select a subject from the suggestions.' : '')
  }, [text, value, busy])
  useEffect(() => {
    if (open) document.getElementById(`${id}-option-${activeIndex}`)?.scrollIntoView?.({ block: 'nearest' })
  }, [open, id, activeIndex])
  async function choose(item) {
    if (busy || disabled) return
    setOpen(false); setError('')
    if (item.key === 'custom') { setCustom(true); return }
    if (!item.key.startsWith('ZW-')) { onChange(Number(item.key)); setQuery(null); return }
    setBusy(true)
    try {
      const [subject] = await saveAcademicRecord('subjects/activate', { keys: [item.key] })
      setExtra((old) => [...old.filter((x) => x.id !== subject.id), subject]); onChange(subject.id); setQuery(null)
    } catch { setError('Subject could not be selected. Connect and try again.'); setOpen(true) }
    finally { setBusy(false) }
  }
  async function addCustom() {
    setBusy(true); setError('')
    try {
      const subject = await saveAcademicRecord('subjects', { name: name.trim(), code: `CUSTOM-${crypto.randomUUID().slice(0, 16)}`, is_active: true })
      setExtra((old) => [...old, subject]); onChange(subject.id); setQuery(null); setCustom(false); setName('')
    } catch { setError('Custom subject could not be saved. Check whether it already exists.') }
    finally { setBusy(false) }
  }
  function keyDown(event) {
    if (busy || disabled) return
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      setHighlight(open ? (activeIndex + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length : event.key === 'ArrowDown' ? 0 : options.length - 1)
      setOpen(true)
    } else if (event.key === 'Enter' && open) { event.preventDefault(); void choose(options[activeIndex]) }
    else if (event.key === 'Escape') { event.preventDefault(); setOpen(false) }
  }
  return <div className="subject-picker" onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false) }}>
    <label htmlFor={id}>Subject</label>
    <input id={id} ref={input} role="combobox" autoComplete="off" placeholder="Search or choose subject..." required={required} disabled={disabled} readOnly={busy} aria-busy={busy} aria-autocomplete="list" aria-expanded={open && !busy} aria-controls={`${id}-suggestions`} aria-activedescendant={open && !busy ? `${id}-option-${activeIndex}` : undefined} value={text}
      onFocus={() => { setOpen(true); setHighlight(0) }} onChange={(event) => { setQuery(event.target.value); onChange(''); setOpen(true); setHighlight(0); setError('') }} onKeyDown={keyDown} />
    {open && !busy && <ul id={`${id}-suggestions`} className="subject-suggestions" role="listbox" aria-label="Subject suggestions">
      {!matches.length && <li role="presentation">No matching subjects.</li>}
      {options.map((item, index) => <li key={item.key} id={`${id}-option-${index}`} role="option" aria-selected={index === activeIndex} onMouseDown={(event) => event.preventDefault()} onClick={() => choose(item)}>{item.name}{item.group && <small>{item.group}</small>}</li>)}
    </ul>}
    {custom && <div><label>Custom subject name<input maxLength="100" value={name} onChange={(event) => setName(event.target.value)} /></label><button type="button" disabled={busy || !name.trim()} onClick={addCustom}>Add custom subject</button><button type="button" onClick={() => setCustom(false)}>Cancel</button></div>}
    {busy && <p role="status">Selecting subject...</p>}{error && <p role="alert">{error}</p>}
  </div>
}
