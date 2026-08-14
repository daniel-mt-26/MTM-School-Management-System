import { useEffect, useRef, useState } from 'react'
import { getStudents } from '../api/students'

export default function StudentPicker({ label = 'Student', selected, schoolClass, onChange, disabled = false, required = false, placeholder = 'Search by name or admission number', excludeStudentIds = [] }) {
  const [query, setQuery] = useState(selected ? labelFor(selected) : '')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const root = useRef(null)

  const canSearch = query.trim().length >= 2 && !(selected && query.trim() === labelFor(selected))
  const excludedStudentIdsKey = excludeStudentIds.map(String).join(',')

  useEffect(() => {
    const term = query.trim()
    if (!canSearch) return undefined
    let active = true
    const timer = setTimeout(() => {
      setLoading(true)
      getStudents({ q: term, school_class: schoolClass || undefined })
        .then((items) => {
          if (!active) return
          const excluded = new Set(excludedStudentIdsKey.split(',').filter(Boolean))
          setResults(items.filter((student) => !excluded.has(String(student.id))))
        })
        .catch(() => active && setResults([]))
        .finally(() => active && setLoading(false))
    }, 250)
    return () => { active = false; clearTimeout(timer) }
  }, [canSearch, excludedStudentIdsKey, query, schoolClass])

  useEffect(() => {
    const close = (event) => { if (!root.current?.contains(event.target)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  function change(event) {
    const value = event.target.value
    setQuery(value); setOpen(true)
    if (selected && value !== labelFor(selected)) onChange(null)
  }

  return <div className="student-picker" ref={root}>
    <label>{label}<input value={query} onChange={change} onFocus={() => setOpen(true)} disabled={disabled} required={required && !selected} placeholder={placeholder} role="combobox" aria-expanded={open} aria-controls="student-picker-results" autoComplete="off" /></label>
    <p className="field-help">{schoolClass ? 'Searching within the selected class.' : 'Search across this school.'}</p>
    {open && canSearch && <div id="student-picker-results" className="student-picker-results" role="listbox">{loading ? <p>Searching students…</p> : results.length ? results.map((student) => <button key={student.id} type="button" role="option" onClick={() => { onChange(student); setQuery(labelFor(student)); setOpen(false) }}><strong>{student.display_name}</strong><span>{student.admission_number} — {student.class_name}</span></button>) : <p>No matching students found.</p>}</div>}
  </div>
}

function labelFor(student) {
  return `${student.display_name} — ${student.admission_number} — ${student.class_name}`
}
