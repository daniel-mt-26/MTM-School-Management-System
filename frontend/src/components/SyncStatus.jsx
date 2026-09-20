import { useContext } from 'react'

import { OfflineContext } from '../offline/context'

export default function SyncStatus() {
  const state = useContext(OfflineContext)
  if (!state?.scope) return null
  const { isReachable, isSyncing, pendingCount, failedCount, lastSyncedAt, syncNow } = state
  const label = !isReachable ? `Offline${pendingCount ? ` — ${pendingCount} waiting` : ''}`
    : isSyncing ? `Syncing${pendingCount ? ` — ${pendingCount} waiting` : ''}`
      : failedCount ? `Sync issue — ${failedCount} need attention`
        : pendingCount ? `Online — ${pendingCount} waiting to sync`
          : 'Online — All changes synced'
  return <aside className={`sync-status ${isReachable ? 'online' : 'offline'}`} aria-live="polite">
    <span>{label}</span>{lastSyncedAt && <small>Last synced: {new Date(lastSyncedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</small>}
    {isReachable && (pendingCount || failedCount) > 0 && <button type="button" onClick={() => syncNow(true)}>Sync Now</button>}
  </aside>
}
