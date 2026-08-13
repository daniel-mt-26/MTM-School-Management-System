import { apiClient } from './client'

export const getParents = (q = '') => apiClient(`/school/parents/${q ? `?q=${encodeURIComponent(q)}` : ''}`)
export const getParent = (id) => apiClient(`/school/parents/${id}/`)
export const createParent = (data) => apiClient('/school/parents/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
export const updateParent = (id, data) => apiClient(`/school/parents/${id}/`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
export const linkParentChild = (data) => apiClient('/school/parent-links/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
export const unlinkParentChild = (id) => apiClient(`/school/parent-links/${id}/`, { method: 'DELETE' })
