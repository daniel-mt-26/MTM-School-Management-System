import { refreshAccessToken, tokenStorage } from './auth.js'

const API_BASE_URL = import.meta.env?.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api'

let refreshPromise = null
let onAuthenticationFailure = () => {}
let applicationRole = null
let applicationScope = null
export function setApplicationRole(role, userId = null) { applicationRole = role; applicationScope = userId == null ? null : `user:${userId}:${role}` }
function rolePath(path) {
  if (applicationRole !== 'teacher') return path
  if (path.startsWith('/school/homework/')) return path.replace('/school/homework/', '/teacher/homework/')
  return path.replace(/^\/school\/(classes|subjects|class-subjects|academic-years|terms)\//, '/teacher/catalog/$1/')
}

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
        if (tokenStorage.getRefresh() !== refresh) throw new Error('Session changed during refresh')
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
  path = rolePath(path)
  const { authenticate = true, expectedScope, ...fetchOptions } = options
  if (expectedScope && expectedScope !== applicationScope) {
    const error = new Error('Reauthenticate as the owner of this queued work.')
    error.code = 'session_expired'; error.status = 401
    throw error
  }
  const headers = new Headers(fetchOptions.headers)
  const access = tokenStorage.getAccess()
  const sessionRefresh = tokenStorage.getRefresh()
  if (authenticate && access) headers.set('Authorization', `Bearer ${access}`)

  let response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...fetchOptions, headers })
  } catch {
    const error = new Error('Network error')
    error.code = 'network_error'
    throw error
  }

  const data = response.status === 204 ? null : await response.json().catch(() => null)
  const blockedCode = data?.code
  if (['school_suspended', 'school_archived'].includes(blockedCode)) {
    onAuthenticationFailure({ code: blockedCode })
    const error = new Error('School access blocked')
    error.status = response.status; error.data = data; error.code = blockedCode
    throw error
  }

  if (authenticate && response.status === 401 && !retried && !path.startsWith('/auth/token/')) {
    if (sessionRefresh !== tokenStorage.getRefresh()) throw new Error('Session changed')
    try {
      await refreshOnce()
      return apiClient(path, options, true)
    } catch {
      if (sessionRefresh !== tokenStorage.getRefresh()) throw new Error('Session changed')
      tokenStorage.clear()
      onAuthenticationFailure()
      const error = new Error('Session expired')
      error.code = 'session_expired'
      throw error
    }
  }

  if (authenticate && response.status === 401 && retried) {
    if (sessionRefresh !== tokenStorage.getRefresh()) throw new Error('Session changed')
    tokenStorage.clear()
    onAuthenticationFailure()
    const error = new Error('Session expired')
    error.code = 'session_expired'
    throw error
  }

  if (!response.ok) {
    const error = new Error('Request failed')
    error.status = response.status
    error.data = data
    throw error
  }
  return data
}

export async function apiDownload(path, filename) {
  path = rolePath(path)
  const access = tokenStorage.getAccess()
  const response = await fetch(`${API_BASE_URL}${path}`, { headers: access ? { Authorization: `Bearer ${access}` } : {} })
  if (!response.ok) throw new Error('Download failed')
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove()
  URL.revokeObjectURL(url)
}

export async function apiOpen(path) {
  const access = tokenStorage.getAccess()
  const response = await fetch(`${API_BASE_URL}${path}`, { headers: access ? { Authorization: `Bearer ${access}` } : {} })
  if (!response.ok) throw new Error('Open failed')
  const url = URL.createObjectURL(await response.blob())
  window.open(url, '_blank', 'noopener,noreferrer')
  window.setTimeout(() => URL.revokeObjectURL(url), 60000)
}
