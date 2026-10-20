import { apiClient } from './client.js'

export const intakeTypes = {
  applications: {
    title: 'Admissions',
    singular: 'Application',
    route: '/school/admissions',
    statuses: {
      pending: 'Pending',
      approved: 'Approved',
      rejected: 'Rejected',
    },
  },
  enquiries: {
    title: 'Enquiries',
    singular: 'Enquiry',
    route: '/school/enquiries',
    statuses: { new: 'New', in_progress: 'In Progress', resolved: 'Resolved' },
  },
}

function pathFor(kind, id) {
  if (!intakeTypes[kind]) throw new Error('Invalid intake type')
  if (
    id &&
    !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(id)
  )
    throw new Error('Invalid record reference')
  return `/school/${kind}/${id ? `${id}/` : ''}`
}
async function request(path, options = {}) {
  if (typeof navigator !== 'undefined' && navigator.onLine === false) {
    const error = new Error('Online connection required')
    error.code = 'network_error'
    throw error
  }
  const controller = new AbortController()
  const abort = () => controller.abort()
  options.signal?.addEventListener('abort', abort, { once: true })
  if (options.signal?.aborted) abort()
  const timer = setTimeout(abort, 20000)
  try {
    return await apiClient(path, {
      ...options,
      cache: 'no-store',
      signal: controller.signal,
    })
  } finally {
    clearTimeout(timer)
    options.signal?.removeEventListener('abort', abort)
  }
}
export async function listIntake(kind, { page = 1, status = '', signal } = {}) {
  if (
    !Number.isInteger(page) ||
    page < 1 ||
    (status && !intakeTypes[kind]?.statuses[status])
  )
    throw new Error('Invalid filter')
  const params = new URLSearchParams({ page: String(page) })
  if (status) params.set('status', status)
  return request(`${pathFor(kind)}?${params}`, { signal })
}
export async function getIntake(kind, id, signal) {
  return request(pathFor(kind, id), { signal })
}
export async function intakeHistory(kind, id, page = 1, signal) {
  return request(`${pathFor(kind, id)}history/?page=${page}`, { signal })
}
export async function reviewIntake(
  kind,
  id,
  { version, status, note },
  signal,
) {
  if (
    !Number.isInteger(version) ||
    version < 1 ||
    (status && !intakeTypes[kind]?.statuses[status])
  )
    throw new Error('Invalid review')
  const body = { version }
  if (status) body.status = status
  if (note?.trim()) body.note = note.trim()
  return request(`${pathFor(kind, id)}review/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
}
export function searchIntakePage(kind, rows, query) {
  const text = query.trim().toLocaleLowerCase()
  return rows.filter((row) =>
    [
      row.reference,
      kind === 'applications' ? row.student_name : row.full_name,
      ...(kind === 'enquiries' ? [row.subject] : []),
    ].some((value) =>
      String(value || '')
        .toLocaleLowerCase()
        .includes(text),
    ),
  )
}
export function intakeError(error) {
  if (error.status === 409)
    return 'Another administrator updated this record. Reload the latest record before reviewing again. Your unsaved note will be discarded on reload.'
  if (error.status === 404)
    return 'This record is unavailable or does not belong to your school.'
  if (error.status === 403)
    return 'Your account is not permitted to access this record.'
  if (error.code === 'session_expired' || error.status === 401)
    return 'Your session has expired. Please sign in again.'
  if (error.status === 400) {
    const message = Object.values(error.data || {})
      .flat()
      .find((value) => typeof value === 'string')
    return message || 'Please check your review details.'
  }
  return 'The request could not be confirmed. Check your connection and reload the record before retrying an update.'
}
