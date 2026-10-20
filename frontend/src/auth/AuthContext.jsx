import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { login, tokenStorage } from '../api/auth'
import { apiClient, setAuthenticationFailureHandler, setApplicationRole } from '../api/client'
import { createSingleFlight } from './session'
import { accountScope, clearOfflineScope } from '../offline/db'
import { AuthContext } from './context'
import { inactivityState } from './inactivity'

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [sessionMessage, setSessionMessage] = useState('')
  const [accessBlocked, setAccessBlocked] = useState(null)
  const userRef = useRef(null)
  const startupRequestStarted = useRef(false)
  const userRequest = useRef(null)
  const authEpoch = useRef(0)
  const [inactivityWarning, setInactivityWarning] = useState(false)

  useEffect(() => {
    if (!user) return
    const key = `mtm:last-activity:${user.id}:${user.role}`
    let lastActivity = Number(localStorage.getItem(key)) || Date.now()
    const record = event => {
      if (event?.target instanceof Element && event.target.closest('.session-warning')) return
      lastActivity = Date.now()
      localStorage.setItem(key, String(lastActivity))
      setInactivityWarning(false)
    }
    const check = () => {
      lastActivity = Math.max(lastActivity, Number(localStorage.getItem(key)) || 0)
      const state = inactivityState(lastActivity, Date.now())
      if (state.expired) {
        authEpoch.current += 1
        tokenStorage.clear()
        setApplicationRole(null)
        setUser(null)
        setSessionMessage('Your session expired due to inactivity. Please sign in again.')
        setInactivityWarning(false)
      } else setInactivityWarning(state.warning)
    }
    if (!localStorage.getItem(key)) record()
    const events = ['pointerdown', 'keydown', 'touchstart']
    events.forEach(event => window.addEventListener(event, record, { passive: true }))
    window.addEventListener('mtm:stay-signed-in', record)
    window.addEventListener('focus', check)
    const timer = setInterval(check, 1000)
    check()
    return () => {
      clearInterval(timer)
      events.forEach(event => window.removeEventListener(event, record))
      window.removeEventListener('mtm:stay-signed-in', record)
      window.removeEventListener('focus', check)
    }
  }, [user])

  useEffect(() => {
    userRef.current = user
  }, [user])

  const logout = useCallback((message = '', preserveOfflineWork = false) => {
    authEpoch.current += 1
    userRequest.current = null
    const scope = accountScope(userRef.current)
    if (scope && !preserveOfflineWork) void clearOfflineScope(scope).catch(() => {})
    tokenStorage.clear()
    setApplicationRole(null)
    setUser(null)
    setAccessBlocked(null)
    setSessionMessage(message)
  }, [])

  const loadCurrentUser = useCallback(() => {
    if (!userRequest.current) {
      userRequest.current = createSingleFlight(() => apiClient('/auth/me/'))
    }
    return userRequest.current()
  }, [])

  useEffect(() => {
    setAuthenticationFailureHandler((reason) => {
      if (reason?.code) { setAccessBlocked(reason.code); return }
      logout('Your session has expired. Please sign in again.', true)
    })
    return () => setAuthenticationFailureHandler(() => {})
  }, [logout])

  useEffect(() => {
    const restoreSession = async () => {
      const epoch = authEpoch.current
      if (startupRequestStarted.current) return
      startupRequestStarted.current = true
      const access = tokenStorage.getAccess()
      if (!access) {
        setIsLoading(false)
        return
      }
      try {
        const profile = await loadCurrentUser()
        if (epoch !== authEpoch.current) return
        setApplicationRole(profile.role, profile.id)
        setUser(profile)
      } catch {
        if (epoch === authEpoch.current) logout('Your session has expired. Please sign in again.', true)
      } finally {
        setIsLoading(false)
      }
    }
    restoreSession()
  }, [loadCurrentUser, logout])

  const signIn = useCallback(async (username, password) => {
    const epoch = ++authEpoch.current
    userRequest.current = null
    const tokens = await login(username, password)
    if (epoch !== authEpoch.current) throw new Error('Session changed')
    const { access, refresh } = tokens ?? {}
    if (typeof access !== 'string' || typeof refresh !== 'string') {
      const error = new Error('Invalid token response')
      error.code = 'post_login_error'
      throw error
    }
    tokenStorage.setTokens({ access, refresh })
    try {
      const profile = await loadCurrentUser()
      if (epoch !== authEpoch.current) throw new Error('Session changed')
      setApplicationRole(profile.role, profile.id)
      localStorage.setItem(`mtm:last-activity:${profile.id}:${profile.role}`, String(Date.now()))
      setUser(profile)
      setAccessBlocked(null)
      setSessionMessage('')
      return profile
    } catch (error) {
      if (epoch === authEpoch.current) tokenStorage.clear()
      error.code = error.code === 'network_error' ? 'network_error' : 'post_login_error'
      throw error
    }
  }, [loadCurrentUser])

  const refreshCurrentUser = useCallback(async () => {
    const epoch = authEpoch.current
    const profile = await loadCurrentUser()
    if (epoch !== authEpoch.current) throw new Error('Session changed')
    setUser(profile)
    return profile
  }, [loadCurrentUser])

  const value = useMemo(() => ({ user, isLoading, sessionMessage, signIn, refreshCurrentUser, logout, accessBlocked }), [user, isLoading, sessionMessage, signIn, refreshCurrentUser, logout, accessBlocked])
  return <AuthContext.Provider value={value}>{children}{user && inactivityWarning && <div className="session-warning" role="alertdialog" aria-modal="true" aria-label="Session expiring"><p>Your session will expire in 2 minutes due to inactivity.</p><button onClick={() => { window.dispatchEvent(new Event('mtm:stay-signed-in')); void refreshCurrentUser().catch(() => logout('Please sign in again.', true)) }}>Stay Signed In</button><button onClick={() => logout('', true)}>Log Out</button></div>}</AuthContext.Provider>
}
