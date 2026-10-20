export const INACTIVITY_MS = 30 * 60 * 1000
export const WARNING_MS = 2 * 60 * 1000

export function inactivityState(lastActivity, now) {
  const remaining = Math.max(0, INACTIVITY_MS - (now - lastActivity))
  return { remaining, expired: remaining === 0, warning: remaining > 0 && remaining <= WARNING_MS }
}
