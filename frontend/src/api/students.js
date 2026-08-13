import { apiClient } from './client'

function queryString(params) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== '' && value !== undefined && value !== null) query.set(key, value)
  })
  const encoded = query.toString()
  return encoded ? `?${encoded}` : ''
}

export function getStudents(filters = {}) {
  return apiClient(`/school/students/${queryString(filters)}`)
}

export function getStudent(studentId) {
  return apiClient(`/school/students/${studentId}/`)
}

export function createStudent(student) {
  return apiClient('/school/students/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(student),
  })
}

export function updateStudent(studentId, student) {
  return apiClient(`/school/students/${studentId}/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(student),
  })
}

export function transferStudent(studentId, transfer) {
  return apiClient(`/school/students/${studentId}/transfer/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(transfer),
  })
}

export function getSchoolClasses() {
  return apiClient('/school/classes/')
}

export function getAvailableParents(query = '') {
  return apiClient(`/school/available-parents/${queryString({ q: query })}`)
}

export function linkParent(link) {
  return apiClient('/school/parent-links/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(link),
  })
}

export function unlinkParent(linkId) {
  return apiClient(`/school/parent-links/${linkId}/`, { method: 'DELETE' })
}
