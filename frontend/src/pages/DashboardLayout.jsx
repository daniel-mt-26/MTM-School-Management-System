import { useContext } from 'react'
import { useNavigate } from 'react-router-dom'
import { AuthContext } from '../auth/context'

export default function DashboardLayout({ title, description }) {
  const { user, logout } = useContext(AuthContext)
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <main className="dashboard-page">
      <header className="dashboard-header">
        <div>
          <p className="brand">MTM School Management System</p>
          <h1>{title}</h1>
        </div>
        <button type="button" className="secondary-button" onClick={handleLogout}>Log out</button>
      </header>
      <section className="dashboard-card">
        <p>Signed in as {user?.first_name || user?.username}.</p>
        <p>{description}</p>
      </section>
    </main>
  )
}
