import { useContext } from 'react'
import { AuthContext } from '../auth/context'
import AccountMenu from '../components/AccountMenu'

export default function DashboardLayout({ title, description }) {
  const { user } = useContext(AuthContext)

  return (
    <main className="dashboard-page">
      <header className="dashboard-header">
        <div className="platform-identity">
          <img className="platform-logo platform-header-logo" src="/mds-logo.png" alt="MDS" />
          <div>
            <p className="brand">MTM School Management System</p>
            <h1>{title}</h1>
          </div>
        </div>
        <AccountMenu />
      </header>
      <section className="dashboard-card">
        <p>Signed in as {user?.first_name || user?.username}.</p>
        <p>{description}</p>
      </section>
    </main>
  )
}
