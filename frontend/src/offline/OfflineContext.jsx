import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { apiClient } from '../api/client'
import { accountScope, queuedOperations, syncMetadata } from './db'
import { processSyncQueue } from './sync'
import { OfflineContext } from './context'

async function backendReachable() {
  if (!navigator.onLine) return false
  try {
    await apiClient('/health/', { headers: { 'Cache-Control': 'no-store' } })
    return true
  } catch {
    return false
  }
}

export function OfflineProvider({ user, children }) {
  const scope = accountScope(user)
  const [isReachable, setIsReachable] = useState(false)
  const [queue, setQueue] = useState([])
  const [metadata, setMetadata] = useState({})
  const [isSyncing, setIsSyncing] = useState(false)
  const [syncRevision, setSyncRevision] = useState(0)
  const syncingRef = useRef(false)

  const refresh = useCallback(async () => {
    if (!scope) { setQueue([]); setMetadata({}); return }
    const [operations, storedMetadata] = await Promise.all([queuedOperations(scope), syncMetadata(scope)])
    setQueue(operations); setMetadata(storedMetadata)
  }, [scope])

  const syncNow = useCallback(async (force = true) => {
    if (!scope || syncingRef.current || !(await backendReachable())) return false
    syncingRef.current = true; setIsSyncing(true)
    try {
      await processSyncQueue(scope, { force, onChange: refresh })
      await refresh()
      setSyncRevision((value) => value + 1)
      return true
    } finally {
      syncingRef.current = false; setIsSyncing(false)
    }
  }, [refresh, scope])

  useEffect(() => {
    const timer = window.setTimeout(() => { void refresh() }, 0)
    return () => window.clearTimeout(timer)
  }, [refresh])

  useEffect(() => {
    let active = true
    const verify = async () => {
      const reachable = await backendReachable()
      if (!active) return
      setIsReachable(reachable)
      if (reachable && scope) await syncNow(false)
    }
    const online = () => { void verify() }
    const offline = () => { if (active) setIsReachable(false) }
    window.addEventListener('online', online)
    window.addEventListener('offline', offline)
    void verify()
    const timer = window.setInterval(verify, 60_000)
    return () => { active = false; window.removeEventListener('online', online); window.removeEventListener('offline', offline); window.clearInterval(timer) }
  }, [scope, syncNow])

  const value = useMemo(() => ({
    scope, isReachable, isSyncing, syncNow, refresh, pendingCount: queue.filter((item) => ['pending', 'syncing'].includes(item.status)).length,
    failedCount: queue.filter((item) => item.status === 'failed').length, lastSyncedAt: metadata.lastSyncedAt ?? null,
    queue, syncRevision,
  }), [isReachable, isSyncing, metadata.lastSyncedAt, queue, refresh, scope, syncNow, syncRevision])
  return <OfflineContext.Provider value={value}>{children}</OfflineContext.Provider>
}
