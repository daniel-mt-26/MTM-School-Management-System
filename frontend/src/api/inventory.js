import { apiClient } from './client'

function queryString(params = {}) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== '' && value !== undefined && value !== null) query.set(key, value)
  })
  return query.toString() ? `?${query}` : ''
}

export const getInventoryCategories = (params) => apiClient(`/school/inventory/categories/${queryString(params)}`)
export const getInventoryItems = (params) => apiClient(`/school/inventory/items/${queryString(params)}`)
export const getInventoryVariants = (params) => apiClient(`/school/inventory/variants/${queryString(params)}`)
export const getInventoryMovements = (params) => apiClient(`/school/inventory/movements/${queryString(params)}`)
export const getInventorySummary = () => apiClient('/school/inventory/summary/')

export function saveInventoryRecord(resource, data, id) {
  return apiClient(`/school/inventory/${resource}/${id ? `${id}/` : ''}`, {
    method: id ? 'PATCH' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}
