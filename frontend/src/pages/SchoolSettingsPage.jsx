import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { getSchoolProfile, updateSchoolProfile } from '../api/school'

const MAX_LOGO_SIZE = 2 * 1024 * 1024

function getInitials(name) {
  return name.trim().split(/\s+/).slice(0, 2).map((word) => word[0]).join('').toUpperCase() || 'S'
}

function SchoolSettingsPage() {
  const [form, setForm] = useState(null)
  const [logoFile, setLogoFile] = useState(null)
  const [preview, setPreview] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    getSchoolProfile()
      .then((profile) => setForm(profile))
      .catch(() => setError('We could not load your school settings. Please try again.'))
  }, [])

  function updateField(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }))
  }

  function selectLogo(event) {
    const file = event.target.files[0]
    setError('')
    if (!file) return
    if (!file.type.startsWith('image/')) {
      setError('Please select a valid image file.')
      event.target.value = ''
      return
    }
    if (file.size > MAX_LOGO_SIZE) {
      setError('The logo must be 2 MB or smaller.')
      event.target.value = ''
      return
    }
    setLogoFile(file)
    const reader = new FileReader()
    reader.onload = () => setPreview(reader.result)
    reader.readAsDataURL(file)
  }

  async function save(event) {
    event.preventDefault()
    setError('')
    setMessage('')
    if (!form.name.trim()) {
      setError('School name is required.')
      return
    }

    setSaving(true)
    try {
      const updated = await updateSchoolProfile({
        name: form.name.trim(),
        email: form.email.trim(),
        phone: form.phone,
        address: form.address,
        default_currency: form.default_currency.trim().toUpperCase(),
      }, logoFile)
      setForm(updated)
      setLogoFile(null)
      setPreview('')
      setMessage('School settings saved successfully.')
    } catch (requestError) {
      const fieldErrors = requestError.data && Object.values(requestError.data).flat()
      setError(fieldErrors?.[0] || 'We could not save your school settings. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  if (error && !form) return <main className="school-profile-state" role="alert">{error}</main>
  if (!form) return <main className="school-profile-state" aria-live="polite">Loading school settings…</main>

  const logoSource = preview || form.logo

  return (
    <main className="school-settings-page">
      <header className="school-settings-header">
        <Link to="/school" className="dashboard-link">← Back to School Dashboard</Link>
        <h1>School Settings</h1>
        <p>Update your school's identity and contact information.</p>
        <Link to="/school/audit" className="dashboard-link">View Audit History</Link>
      </header>

      <form className="school-settings-form" onSubmit={save}>
        <div className="settings-logo-row">
          {logoSource ? (
            <img className="settings-logo" src={logoSource} alt={`${form.name} logo preview`} />
          ) : (
            <div className="settings-logo" aria-hidden="true">{getInitials(form.name)}</div>
          )}
          <label className="logo-picker">
            School Logo
            <input type="file" accept="image/*" onChange={selectLogo} />
            <span>PNG, JPEG, GIF or another supported image, up to 2 MB.</span>
          </label>
        </div>

        <label>School Name<input name="name" value={form.name} onChange={updateField} required /></label>
        <label>School Email<input name="email" type="email" value={form.email} onChange={updateField} required /></label>
        <label>Phone Number<input name="phone" value={form.phone} onChange={updateField} required /></label>
        <label>Address<textarea name="address" value={form.address} onChange={updateField} rows="4" /></label>
        <label>Default Currency<input name="default_currency" value={form.default_currency} onChange={updateField} maxLength="3" placeholder="USD" required /><span className="field-help">Three-letter operational currency code. It cannot be changed after finance records exist.</span></label>

        {error && <p className="form-error" role="alert">{error}</p>}
        {message && <p className="form-success" role="status">{message}</p>}

        <div className="settings-actions">
          <button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save Changes'}</button>
          <Link to="/school" className="settings-cancel">Cancel</Link>
        </div>
      </form>
    </main>
  )
}

export default SchoolSettingsPage
