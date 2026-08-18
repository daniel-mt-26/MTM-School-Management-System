import { useContext, useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { AuthContext } from '../auth/context'
import { routeForRole } from '../auth/roleRoutes'

export default function LoginPage() {
  const { user, signIn, sessionMessage } = useContext(AuthContext)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(sessionMessage)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  if (user) return <Navigate to={routeForRole(user.role)} replace />

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')
    setIsSubmitting(true)
    try {
      const profile = await signIn(username, password)
      const requestedPath = location.state?.from?.pathname
      const destination = requestedPath && requestedPath === routeForRole(profile.role)
        ? requestedPath
        : routeForRole(profile.role)
      navigate(destination, { replace: true })
    } catch (requestError) {
      if (requestError.code === 'invalid_credentials') {
        setError('Your username or password is incorrect.')
      } else if (requestError.code === 'network_error') {
        setError('We could not reach the MTM server. Please try again.')
      } else {
        setError('You signed in, but the application could not load your account. Please try again.')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="login-page">
      <section className="login-card" aria-labelledby="login-title">
        <img className="platform-logo login-logo" src="/mds-logo.png" alt="MDS" />
        <p className="brand">MTM School Management System</p>
        <h1 id="login-title">Sign in</h1>
        <p className="login-copy">Use your MTM account to continue.</p>
        {(error || sessionMessage) && <p className="form-error" role="alert">{error || sessionMessage}</p>}
        <form onSubmit={handleSubmit}>
          <label htmlFor="username">Username</label>
          <input id="username" name="username" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required />
          <label htmlFor="password">Password</label>
          <input id="password" name="password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />
          <button type="submit" disabled={isSubmitting}>{isSubmitting ? 'Signing in…' : 'Sign in'}</button>
        </form>
      </section>
    </main>
  )
}
