import { useState } from 'react'
import { Link } from 'react-router-dom'
import { apiClient } from '../api/client'
import Attribution from '../components/Attribution'

export default function PasswordRecoveryPage({ reset = false }) {
  const [value, setValue] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [token] = useState(() => {
    const value = new URLSearchParams(window.location.hash.slice(1)).get('token') || ''
    if (reset) window.history.replaceState(null, '', window.location.pathname)
    return value
  })
  async function submit(event) {
    event.preventDefault(); setBusy(true); setNotice('')
    try {
      const data = await apiClient(`/auth/${reset ? 'reset' : 'forgot'}-password/`, { authenticate: false, method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(reset ? { token, new_password: value } : { identifier: value }) })
      setNotice(data.detail); setValue('')
    } catch (error) { setNotice(Object.values(error.data || {}).flat().join(' ') || 'Recovery is unavailable. Please try again later or contact your administrator.') }
    finally { setBusy(false) }
  }
  return <main className="login-page"><section className="login-card"><h1>{reset ? 'Choose a new password' : 'Forgot password?'}</h1><form onSubmit={submit}><label>{reset ? 'New password' : 'Username or email'}<input type={reset ? 'password' : 'text'} autoComplete={reset ? 'new-password' : 'username'} value={value} onChange={e => setValue(e.target.value)} required /></label><button disabled={busy}>{reset ? 'Reset password' : 'Send reset instructions'}</button></form>{notice && <p role="status">{notice}</p>}<Link to="/login">Back to login</Link><Attribution /></section></main>
}
