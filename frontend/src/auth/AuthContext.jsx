import { useCallback, useEffect, useMemo, useState } from 'react'
import { getCurrentUser, login, tokenStorage } from '../api/auth'
import { apiClient, setAuthenticationFailureHandler } from '../api/client'
import { accountScope, clearOfflineScope } from '../offline/db'
import { AuthContext } from './context'

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [sessionMessage, setSessionMessage] = useState('')
  const [accessBlocked, setAccessBlocked] = useState(null)

  const logout = useCallback((message = '', preserveOfflineWork = false) => {
    const scope = accountScope(user)
    if (scope && !preserveOfflineWork) void clearOfflineScope(scope).catch(() => {})
    tokenStorage.clear()
    setUser(null)
    setAccessBlocked(null)
    setSessionMessage(message)
  }, [user])

  useEffect(() => {
    setAuthenticationFailureHandler((reason) => {
      if (reason?.code) { setAccessBlocked(reason.code); return }
      logout('Your session has expired. Please sign in again.', true)
    })
    return () => setAuthenticationFailureHandler(() => {})
  }, [logout])

  useEffect(() => {
    const restoreSession = async () => {
      const access = tokenStorage.getAccess()
      if (!access) {
        setIsLoading(false)
        return
      }
      try {
        setUser(await apiClient('/auth/me/'))
      } catch {
        logout('Your session has expired. Please sign in again.', true)
      } finally {
        setIsLoading(false)
      }
    }
    restoreSession()
  }, [logout])

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
      const profile = await getCurrentUser(access)
      setUser(profile)
      setAccessBlocked(null)
      setSessionMessage('')
      return profile
    } catch (error) {
      tokenStorage.clear()
      error.code = error.code === 'network_error' ? 'network_error' : 'post_login_error'
      throw error
    }
  }, [])

  const value = useMemo(() => ({ user, isLoading, sessionMessage, signIn, logout, accessBlocked }), [user, isLoading, sessionMessage, signIn, logout, accessBlocked])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
