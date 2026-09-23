import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { login, tokenStorage } from '../api/auth'
import { apiClient, setAuthenticationFailureHandler } from '../api/client'
import { createSingleFlight } from './session'
import { accountScope, clearOfflineScope } from '../offline/db'
import { AuthContext } from './context'

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [sessionMessage, setSessionMessage] = useState('')
  const [accessBlocked, setAccessBlocked] = useState(null)
  const userRef = useRef(null)
  const startupRequestStarted = useRef(false)
  const userRequest = useRef(null)

  useEffect(() => {
    userRef.current = user
  }, [user])

  const logout = useCallback((message = '', preserveOfflineWork = false) => {
    const scope = accountScope(userRef.current)
    if (scope && !preserveOfflineWork) void clearOfflineScope(scope).catch(() => {})
    tokenStorage.clear()
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
      if (startupRequestStarted.current) return
      startupRequestStarted.current = true
      const access = tokenStorage.getAccess()
      if (!access) {
        setIsLoading(false)
        return
      }
      try {
        setUser(await loadCurrentUser())
      } catch {
        logout('Your session has expired. Please sign in again.', true)
      } finally {
        setIsLoading(false)
      }
    }
    restoreSession()
  }, [loadCurrentUser, logout])

  const signIn = useCallback(async (username, password) => {
    const tokens = await login(username, password)
    const { access, refresh } = tokens ?? {}
    if (typeof access !== 'string' || typeof refresh !== 'string') {
      const error = new Error('Invalid token response')
      error.code = 'post_login_error'
      throw error
    }
    tokenStorage.setTokens({ access, refresh })
    try {
      const profile = await loadCurrentUser()
      setUser(profile)
      setAccessBlocked(null)
      setSessionMessage('')
      return profile
    } catch (error) {
      tokenStorage.clear()
      error.code = error.code === 'network_error' ? 'network_error' : 'post_login_error'
      throw error
    }
  }, [loadCurrentUser])

  const refreshCurrentUser = useCallback(async () => {
    const profile = await loadCurrentUser()
    setUser(profile)
    return profile
  }, [loadCurrentUser])

  const value = useMemo(() => ({ user, isLoading, sessionMessage, signIn, refreshCurrentUser, logout, accessBlocked }), [user, isLoading, sessionMessage, signIn, refreshCurrentUser, logout, accessBlocked])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
