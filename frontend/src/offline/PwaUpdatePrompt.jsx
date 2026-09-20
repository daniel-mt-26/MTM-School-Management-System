import { useEffect, useRef, useState } from 'react'
import { registerSW } from 'virtual:pwa-register'

export default function PwaUpdatePrompt() {
  const [offlineReady, setOfflineReady] = useState(false)
  const [updateAvailable, setUpdateAvailable] = useState(false)
  const updateServiceWorker = useRef(null)

  useEffect(() => {
    const update = registerSW({
      onOfflineReady() { setOfflineReady(true) },
      onNeedRefresh() { setUpdateAvailable(true) },
    })
    updateServiceWorker.current = update
  }, [])

  if (!offlineReady && !updateAvailable) return null
  return <aside className="pwa-update-notice" role="status">
    <span>{updateAvailable ? 'A new version is ready.' : 'MTM SMS is ready to open offline.'}</span>
    {updateAvailable ? <button type="button" onClick={() => updateServiceWorker.current?.(true)}>Refresh</button> : <button type="button" onClick={() => setOfflineReady(false)}>OK</button>}
  </aside>
}
