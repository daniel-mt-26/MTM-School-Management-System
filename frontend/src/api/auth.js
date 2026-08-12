const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api'

export const tokenStorage = {
  getAccess: () => sessionStorage.getItem('mtm_access_token'),
  getRefresh: () => sessionStorage.getItem('mtm_refresh_token'),
  setTokens: ({ access, refresh }) => {
    sessionStorage.setItem('mtm_access_token', access)
    sessionStorage.setItem('mtm_refresh_token', refresh)
  },
  setAccess: (access) => sessionStorage.setItem('mtm_access_token', access),
  clear: () => {
    sessionStorage.removeItem('mtm_access_token')
    sessionStorage.removeItem('mtm_refresh_token')
  },
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, options)
  const data = response.status === 204 ? null : await response.json().catch(() => null)

  if (!response.ok) {
    const error = new Error('Request failed')
    error.status = response.status
    error.data = data
    throw error
  }

  return data
}

export function login(username, password) {
  return request('/auth/token/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
}

export function refreshAccessToken(refresh) {
  return request('/auth/token/refresh/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh }),
  })
}

export function getCurrentUser(accessToken) {
  return request('/auth/me/', {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
}
