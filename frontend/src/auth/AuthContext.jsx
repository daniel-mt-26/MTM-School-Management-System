import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { login, tokenStorage } from '../api/auth'
import { apiClient, setAuthenticationFailureHandler, setApplicationRole } from '../api/client'
import { createSingleFlight } from './session'
import { accountScope, clearOfflineScope } from '../offline/db'
import { AuthContext } from './context'
import { beginSession, monitorInactivity, publishLogout, rememberSessionAccount, sessionEndReason, storedSessionAccount } from './inactivity'

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [sessionMessage, setSessionMessage] = useState('')
  const [accessBlocked, setAccessBlocked] = useState(null)
  const userRef = useRef(null)
  const startupRequestStarted = useRef(false)
  const userRequest = useRef(null)
  const authEpoch = useRef(0)
  const sessionEnded = useRef(false)
  const [inactivityWarning, setInactivityWarning] = useState(false)
  const logout = useCallback((message = '', preserveOfflineWork = false, broadcast = true) => {
    if (sessionEnded.current) return
    sessionEnded.current = true
    authEpoch.current += 1
    userRequest.current = null
    const currentUser = userRef.current
    userRef.current = null
    const scope = accountScope(currentUser)
    if (scope && !preserveOfflineWork) void clearOfflineScope(scope).catch(() => {})
    tokenStorage.clear()
    setApplicationRole(null)
    setUser(null)
    setAccessBlocked(null)
    setSessionMessage(message)
    setInactivityWarning(false)
    if (currentUser && broadcast) publishLogout(currentUser, message, preserveOfflineWork)
  }, [])

  useEffect(() => {
    if (!user) return
    return monitorInactivity(user, {
      onEnd: reason => logout(reason.message, reason.preserveOfflineWork, !reason.id),
      onWarning: setInactivityWarning,
    })
  }, [user, logout])

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
      // Check before any network request, including while offline or resuming
      // a tab whose storage event was suspended by the browser.
      const account = storedSessionAccount()
      if (account) {
        userRef.current = account
        const reason = sessionEndReason(account)
        if (reason) {
          logout(reason.message, reason.preserveOfflineWork, !reason.id)
          setIsLoading(false)
          return
        }
      }
      try {
        const profile = await loadCurrentUser()
        if (epoch !== authEpoch.current) return
        userRef.current = profile
        const reason = sessionEndReason(profile)
        if (reason) {
          logout(reason.message, reason.preserveOfflineWork, !reason.id)
          return
        }
        rememberSessionAccount(profile)
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
    sessionEnded.current = false
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
      beginSession(profile)
      userRef.current = profile
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
    userRef.current = profile
    setUser(profile)
    return profile
  }, [loadCurrentUser])

  const value = useMemo(() => ({ user, isLoading, sessionMessage, signIn, refreshCurrentUser, logout, accessBlocked }), [user, isLoading, sessionMessage, signIn, refreshCurrentUser, logout, accessBlocked])
  return <AuthContext.Provider value={value}>{children}{user && inactivityWarning && <div className="session-warning" role="status"><p>Your session will expire in 2 minutes due to inactivity.</p><p>Click, type, or scroll to stay signed in.</p></div>}</AuthContext.Provider>
}
