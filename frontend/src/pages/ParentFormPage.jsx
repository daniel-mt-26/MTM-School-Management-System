import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { createParent, getParent, updateParent } from '../api/parents'

const emptyForm = { username: '', first_name: '', last_name: '', email: '', phone_number: '', address: '', password: '' }

export default function ParentFormPage() {
  const { parentId } = useParams()
  const editing = Boolean(parentId)
  const [form, setForm] = useState(emptyForm)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(editing)
  const navigate = useNavigate()

  useEffect(() => {
    if (!editing) return
    getParent(parentId).then((parent) => setForm({ username: parent.username, first_name: parent.first_name, last_name: parent.last_name, email: parent.email || '', phone_number: parent.phone_number, address: parent.address || '', password: '' })).catch(() => setError('We could not load this parent or guardian.')).finally(() => setLoading(false))
  }, [editing, parentId])

  const change = (event) => setForm({ ...form, [event.target.name]: event.target.value })
  async function submit(event) {
    event.preventDefault()
    setError('')
    try {
      const payload = { ...form }
      if (editing && !payload.password) delete payload.password
      const parent = editing ? await updateParent(parentId, payload) : await createParent(payload)
      navigate(`/school/parents/${parent.id}`)
    } catch (requestError) {
      setError(Object.values(requestError.data || {}).flat().join(' ') || 'We could not save the parent.')
    }
  }

  if (loading) return <main className="school-profile-state">Loading parent…</main>
  const back = editing ? `/school/parents/${parentId}` : '/school/parents'
  return <main className="student-page"><header className="student-page-header"><div><Link to={back} className="dashboard-link">Back to Parents</Link><h1>{editing ? 'Edit Parent or Guardian' : 'Add Parent or Guardian'}</h1></div></header><form className="student-form" onSubmit={submit}>
    <div className="form-columns"><label>First Name<input name="first_name" value={form.first_name} onChange={change} /></label><label>Last Name<input name="last_name" value={form.last_name} onChange={change} /></label></div>
    <div className="form-columns"><label>Email<input name="email" type="email" value={form.email} onChange={change} /></label><label>Phone<input name="phone_number" value={form.phone_number} onChange={change} required /></label></div>
    <label>Address<textarea name="address" value={form.address} onChange={change} rows="3" /></label>
    <div className="form-columns"><label>Username<input name="username" value={form.username} onChange={change} required /></label><label>{editing ? 'New Password (optional)' : 'Initial Password'}<input name="password" type="password" value={form.password} onChange={change} required={!editing} /><span className="field-help">{editing ? 'Leave blank to keep the existing password.' : 'The parent uses this to sign in.'}</span></label></div>
    {error && <p className="form-error">{error}</p>}<div className="settings-actions"><button>{editing ? 'Save Changes' : 'Save Parent'}</button><Link to={back} className="settings-cancel">Cancel</Link></div>
  </form></main>
}
