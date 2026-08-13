import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { createStudent, getSchoolClasses, getStudent, transferStudent, updateStudent } from '../api/students'

const EMPTY_FORM = { admission_number: '', first_name: '', last_name: '', date_of_birth: '', school_class: '', enrolled_on: '', is_active: true }

function apiMessage(error) {
  if (error.status === 404) return 'Student not found.'
  const errors = error.data && Object.values(error.data).flat()
  return errors?.[0] || 'We could not save the student. Please try again.'
}

function StudentFormPage() {
  const { studentId } = useParams()
  const editing = Boolean(studentId)
  const navigate = useNavigate()
  const [form, setForm] = useState(EMPTY_FORM)
  const [classes, setClasses] = useState([])
  const [originalClass, setOriginalClass] = useState('')
  const [transferEffectiveDate, setTransferEffectiveDate] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const requests = [getSchoolClasses()]
    if (editing) requests.push(getStudent(studentId))
    Promise.all(requests)
      .then(([classData, student]) => {
        setClasses(classData.filter((item) => item.is_active || item.id === student?.school_class))
        if (student) {
          const currentClass = String(student.school_class)
          setOriginalClass(currentClass)
          setForm({
            admission_number: student.admission_number, first_name: student.first_name, last_name: student.last_name,
            date_of_birth: student.date_of_birth, school_class: currentClass, enrolled_on: student.enrolled_on, is_active: student.is_active,
          })
        }
      })
      .catch((requestError) => setError(requestError.status === 404 ? 'Student not found.' : 'We could not load the student form.'))
      .finally(() => setLoading(false))
  }, [editing, studentId])

  function change(event) {
    const { name, type, checked, value } = event.target
    setForm((current) => ({ ...current, [name]: type === 'checkbox' ? checked : value }))
  }

  async function submit(event) {
    event.preventDefault(); setError(''); setSaving(true)
    try {
      let saved
      if (editing) {
        const classChanged = form.school_class !== originalClass
        if (classChanged && !transferEffectiveDate) {
          setError('Transfer effective date is required when changing class.')
          setSaving(false)
          return
        }
        const studentDetails = {
          admission_number: form.admission_number,
          first_name: form.first_name,
          last_name: form.last_name,
          date_of_birth: form.date_of_birth,
          enrolled_on: form.enrolled_on,
          is_active: form.is_active,
        }
        saved = await updateStudent(studentId, studentDetails)
        if (classChanged) {
          saved = await transferStudent(studentId, {
            school_class: Number(form.school_class),
            transfer_effective_date: transferEffectiveDate,
          })
        }
      } else {
        saved = await createStudent(form)
      }
      navigate(`/school/students/${saved.id}`, { replace: true })
    } catch (requestError) {
      setError(apiMessage(requestError))
    } finally { setSaving(false) }
  }

  if (loading) return <main className="school-profile-state">Loading student form…</main>

  return (
    <main className="student-page">
      <header className="student-page-header"><div><Link to={editing ? `/school/students/${studentId}` : '/school/students'} className="dashboard-link">← Back</Link><h1>{editing ? 'Edit Student' : 'Add Student'}</h1></div></header>
      <form className="student-form" onSubmit={submit}>
        <label>Admission Number<input name="admission_number" value={form.admission_number} onChange={change} required /></label>
        <div className="form-columns"><label>First Name<input name="first_name" value={form.first_name} onChange={change} required /></label><label>Last Name<input name="last_name" value={form.last_name} onChange={change} required /></label></div>
        <div className="form-columns"><label>Date of Birth<input name="date_of_birth" type="date" value={form.date_of_birth} onChange={change} required /></label><label>Enrolled On<input name="enrolled_on" type="date" value={form.enrolled_on} onChange={change} required /></label></div>
        <label>Current Class<select name="school_class" value={form.school_class} onChange={change} required><option value="">Select a class</option>{classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        {editing && form.school_class !== originalClass && (
          <label>Transfer Effective Date
            <input type="date" value={transferEffectiveDate} onChange={(event) => setTransferEffectiveDate(event.target.value)} required />
            <span className="field-help">The previous class enrollment will end the day before this date.</span>
          </label>
        )}
        <label className="checkbox-label"><input name="is_active" type="checkbox" checked={form.is_active} onChange={change} /> Student is active</label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="settings-actions"><button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save Student'}</button><Link to={editing ? `/school/students/${studentId}` : '/school/students'} className="settings-cancel">Cancel</Link></div>
      </form>
    </main>
  )
}

export default StudentFormPage
