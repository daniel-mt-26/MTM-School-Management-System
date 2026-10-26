import { useContext } from 'react'
import { AuthContext } from '../auth/context'

export default function AccountMenu({ preserveOfflineWork = false }) {
  const { logout } = useContext(AuthContext)
  return (
    <nav className="account-menu" aria-label="Account menu">
      <button type="button" className="secondary-button" onClick={() => logout('', preserveOfflineWork)}>Logout</button>
    </nav>
  )
}
