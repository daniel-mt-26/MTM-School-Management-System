export const INACTIVITY_MS = 600 * 1000
export const WARNING_MS = 2 * 60 * 1000
export const INACTIVITY_MESSAGE = 'Your session has expired after 10 minutes of inactivity. Please log in again.'

const activityKey = user => `mtm:last-activity:${user.id}:${user.role}`
const logoutKey = user => `mtm:logout:${user.id}:${user.role}`

export function rememberSessionAccount(user) {
  sessionStorage.setItem('mtm_session_account', JSON.stringify({ id: user.id, role: user.role }))
}

export function storedSessionAccount() {
  try {
    const account = JSON.parse(sessionStorage.getItem('mtm_session_account'))
    return account?.id != null && typeof account.role === 'string' ? account : null
  } catch { return null }
}

export function beginSession(user) {
  rememberSessionAccount(user)
  sessionStorage.setItem(logoutKey(user), localStorage.getItem(logoutKey(user)) || '')
  localStorage.setItem(activityKey(user), String(Date.now()))
}

export function publishLogout(user, message, preserveOfflineWork) {
  localStorage.setItem(logoutKey(user), JSON.stringify({
    id: crypto.randomUUID(), message, preserveOfflineWork,
  }))
}

export function sessionEndReason(user) {
  const signal = localStorage.getItem(logoutKey(user)) || ''
  if (signal !== (sessionStorage.getItem(logoutKey(user)) || '')) {
    try { return JSON.parse(signal) } catch { return { message: '', preserveOfflineWork: true } }
  }
  const lastActivity = localStorage.getItem(activityKey(user))
  if ((lastActivity === null && storedSessionAccount()) || (lastActivity !== null &&
    (!Number.isFinite(Number(lastActivity)) || inactivityState(Number(lastActivity), Date.now()).expired))) {
    return { message: INACTIVITY_MESSAGE, preserveOfflineWork: true }
  }
  return null
}

export function inactivityState(lastActivity, now) {
  const remaining = Math.max(0, INACTIVITY_MS - (now - lastActivity))
  return { remaining, expired: remaining === 0, warning: remaining > 0 && remaining <= WARNING_MS }
}

// One deadline timer per provider. Only input events record activity; resume events
// check the persisted deadline before a returning user can extend the session.
export function monitorInactivity(user, { onEnd, onWarning }) {
  let timer, stopped = false
  if (localStorage.getItem(activityKey(user)) === null) {
    localStorage.setItem(activityKey(user), String(Date.now()))
  }
  const check = () => {
    if (stopped) return false
    clearTimeout(timer)
    const reason = sessionEndReason(user)
    if (reason) {
      stopped = true
      onEnd(reason)
      return false
    }
    const state = inactivityState(Number(localStorage.getItem(activityKey(user))), Date.now())
    onWarning(state.warning)
    timer = setTimeout(check, state.warning ? state.remaining : state.remaining - WARNING_MS)
    return true
  }
  const record = event => {
    // Script-generated events and background work cannot prolong a session.
    if (!event.isTrusted || !check()) return
    localStorage.setItem(activityKey(user), String(Date.now()))
    check()
  }
  const sync = event => {
    if (event.key === activityKey(user) || event.key === logoutKey(user) || event.key === null) check()
  }
  const events = ['pointerdown', 'click', 'keydown', 'scroll', 'touchstart', 'touchmove', 'wheel']
  const options = { capture: true, passive: true }
  events.forEach(event => window.addEventListener(event, record, options))
  window.addEventListener('storage', sync)
  window.addEventListener('focus', check)
  window.addEventListener('pageshow', check)
  document.addEventListener('visibilitychange', check)
  check()
  return () => {
    stopped = true
    clearTimeout(timer)
    events.forEach(event => window.removeEventListener(event, record, options))
    window.removeEventListener('storage', sync)
    window.removeEventListener('focus', check)
    window.removeEventListener('pageshow', check)
    document.removeEventListener('visibilitychange', check)
  }
}
