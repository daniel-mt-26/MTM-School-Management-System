import { apiClient, apiDownload, apiOpen } from './client'

const query = (params) => { const value = new URLSearchParams(Object.entries(params).filter(([, item]) => item !== '' && item != null)).toString(); return value ? `?${value}` : '' }
export const getHomework = (params = {}) => apiClient(`/school/homework/${query(params)}`)
export const saveHomework = (formData, id) => apiClient(`/school/homework/${id ? `${id}/` : ''}`, { method: id ? 'PATCH' : 'POST', body: formData })
export const deleteHomework = (id) => apiClient(`/school/homework/${id}/`, { method: 'DELETE' })
export const removeHomeworkAttachment = (homeworkId, attachmentId) => apiClient(`/school/homework/${homeworkId}/attachments/${attachmentId}/`, { method: 'DELETE' })
export const downloadHomeworkAttachment = (scope, homeworkId, attachment, student = '') => apiDownload(`/${scope}/homework/${homeworkId}/attachments/${attachment.id}/download/${student ? `?student=${student}` : ''}`, attachment.original_name)
export const openHomeworkAttachment = (homeworkId, attachment, student) => apiOpen(`/parent/homework/${homeworkId}/attachments/${attachment.id}/download/?student=${student}`)
export const getParentHomework = (student, history = false) => apiClient(`/parent/homework/?student=${student}&history=${history}`)
