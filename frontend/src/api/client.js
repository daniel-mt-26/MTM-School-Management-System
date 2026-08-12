import { refreshAccessToken, tokenStorage } from './auth'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api'

let refreshPromise = null
let onAuthenticationFailure = () => {}

export function setAuthenticationFailureHandler(handler) {
  onAuthenticationFailure = handler
}

async function refreshOnce() {
  if (!refreshPromise) {
    const refresh = tokenStorage.getRefresh()
    if (!refresh) {
      throw new Error('No refresh token')
    }

    refreshPromise = refreshAccessToken(refresh)
      .then(({ access }) => {
        tokenStorage.setAccess(access)
        return access
      })
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

export async function apiClient(path, options = {}, retried = false) {
  const headers = new Headers(options.headers)
  const access = tokenStorage.getAccess()
  if (access) headers.set('Authorization', `Bearer ${access}`)

  let response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers })
  } catch {
    const error = new Error('Network error')
    error.code = 'network_error'
    throw error
  }

  if (response.status === 401 && !retried && !path.startsWith('/auth/token/')) {
    try {
      await refreshOnce()
      return apiClient(path, options, true)
    } catch {
      tokenStorage.clear()
      onAuthenticationFailure()
      const error = new Error('Session expired')
      error.code = 'session_expired'
      throw error
    }
  }

  const data = response.status === 204 ? null : await response.json().catch(() => null)
  if (!response.ok) {
    const error = new Error('Request failed')
    error.status = response.status
    error.data = data
    throw error
  }
  return data
}
