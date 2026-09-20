import { useContext } from 'react'
import { Outlet } from 'react-router-dom'

import { AuthContext } from '../auth/context'
import SyncStatus from '../components/SyncStatus'
import { OfflineProvider } from '../offline/OfflineContext'

export default function SchoolOfflineShell() {
  const { user } = useContext(AuthContext)
  return <OfflineProvider user={user}><SyncStatus /><Outlet /></OfflineProvider>
}
