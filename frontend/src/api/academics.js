import { apiClient } from './client'

function queryString(params = {}) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => { if (value !== '' && value !== undefined && value !== null) query.set(key, value) })
  return query.toString() ? `?${query}` : ''
}

export const getAcademicRecords = (resource, params = {}) => apiClient(`/school/${resource}/${queryString(params)}`)
export const saveAcademicRecord = (resource, data, id) => apiClient(`/school/${resource}/${id ? `${id}/` : ''}`, { method: id ? 'PATCH' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
export const removeAcademicRecord = (resource, id) => apiClient(`/school/${resource}/${id}/`, { method: 'DELETE' })
