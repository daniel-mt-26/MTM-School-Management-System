import { apiClient } from './client'

function query(params) {
  const values = new URLSearchParams(params)
  return values.toString()
}

export const getAttendanceRoster = (params) => apiClient(`/school/attendance/roster/?${query(params)}`)
export const saveAttendanceBulk = (payload, idempotencyKey) => apiClient('/school/attendance/bulk/', {
  method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey }, body: JSON.stringify(payload),
})
