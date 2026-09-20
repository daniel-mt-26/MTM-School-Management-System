import { cacheValue, cachedValue, enqueueOperation, queuedOperations, syncMetadata, updateSyncMetadata } from './db.js'

const rosterKey = (context) => `attendance:roster:${context.school_class}:${context.academic_year}:${context.term}:${context.attendance_date}`

export async function cacheAttendanceRoster(scope, roster) {
  const value = { ...roster, cachedAt: new Date().toISOString() }
  await cacheValue(scope, rosterKey(value), value)
  const metadata = await syncMetadata(scope)
  const context = { school_class: value.school_class, class_name: value.class_name, academic_year: value.academic_year, academic_year_name: value.academic_year_name, term: value.term, term_name: value.term_name, attendance_date: value.attendance_date }
  const contexts = [...(metadata.attendanceContexts ?? []).filter((entry) => rosterKey(entry) !== rosterKey(context)), context].slice(-20)
  await updateSyncMetadata(scope, { attendanceCachedAt: value.cachedAt, attendanceContexts: contexts })
  return value
}

export const cachedAttendanceRoster = (scope, context) => cachedValue(scope, rosterKey(context))

export async function queueAttendanceBulk(scope, payload) {
  const id = crypto.randomUUID()
  return enqueueOperation(scope, { id, module: 'attendance', entity: 'bulk', entityId: `${payload.school_class}:${payload.attendance_date}`, action: 'save', method: 'POST', path: '/school/attendance/bulk/', payload })
}

export async function attendanceWithLocalChanges(scope, roster) {
  if (!roster) return null
  const operations = await queuedOperations(scope)
  const relevant = operations.filter((operation) => operation.module === 'attendance' && operation.entity === 'bulk' && operation.payload.school_class === roster.school_class && operation.payload.academic_year === roster.academic_year && operation.payload.term === roster.term && operation.payload.attendance_date === roster.attendance_date)
  const latest = new Map()
  relevant.forEach((operation) => operation.payload.entries.forEach((entry) => latest.set(entry.enrollment, { ...entry, syncStatus: operation.status, syncOperationId: operation.id, failureCategory: operation.failureCategory, failureMessage: operation.failureMessage })))
  return { ...roster, students: roster.students.map((student) => latest.has(student.enrollment) ? { ...student, attendance: { status: latest.get(student.enrollment).status, updated_at: student.attendance?.updated_at ?? null }, syncStatus: latest.get(student.enrollment).syncStatus, syncOperationId: latest.get(student.enrollment).syncOperationId } : student), hasLocalChanges: relevant.length > 0 }
}
