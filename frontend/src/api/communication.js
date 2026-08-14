import { apiClient } from './client'

const json = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
const query = (params = {}) => {
  const values = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => { if (value !== '' && value !== undefined && value !== null) values.set(key, value) })
  return values.toString() ? `?${values}` : ''
}

export const getCommunicationSettings = () => apiClient('/school/communication/settings/')
export const updateCommunicationSettings = (values) => apiClient('/school/communication/settings/', json('PATCH', values))
export const getAnnouncements = () => apiClient('/school/communication/announcements/')
export const createAnnouncement = (values) => apiClient('/school/communication/announcements/', json('POST', values))
export const previewAnnouncement = (id) => apiClient(`/school/communication/announcements/${id}/preview/`)
export const sendAnnouncement = (id) => apiClient(`/school/communication/announcements/${id}/send/`, json('POST', { confirm: true }))
export const getCommunicationHistory = (filters) => apiClient(`/school/communication/history/${query(filters)}`)
export const sendFeeReminders = (studentIds = []) => apiClient('/school/communication/fee-reminders/', json('POST', { student_ids: studentIds }))
export const getParentCommunicationPreference = () => apiClient('/parent/communication/preference/')
export const updateParentCommunicationPreference = (values) => apiClient('/parent/communication/preference/', json('PATCH', values))
export const getParentNotifications = () => apiClient('/parent/notifications/')
export const markNotificationRead = (id) => apiClient(`/parent/notifications/${id}/mark-read/`, json('POST', {}))
