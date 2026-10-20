import { useContext, useEffect, useState } from 'react'
import { Link, Outlet } from 'react-router-dom'
import { AuthContext } from '../auth/context'

export default function IntakeOnlineBoundary() {
  const { user } = useContext(AuthContext)
  const [online, setOnline] = useState(() => navigator.onLine)
  useEffect(() => {
    const connected = () => setOnline(true),
      disconnected = () => setOnline(false)
    window.addEventListener('online', connected)
    window.addEventListener('offline', disconnected)
    return () => {
      window.removeEventListener('online', connected)
      window.removeEventListener('offline', disconnected)
    }
  }, [])
  if (!online)
    return (
      <main className="student-page">
        <section className="student-state" role="status">
          <h1>Online connection required</h1>
          <p>
            Admissions and enquiries are available online only. Connect to load
            current records. No intake information is saved for offline access.
          </p>
          <Link to="/school" className="dashboard-link">
            Back to School Dashboard
          </Link>
        </section>
      </main>
    )
  return <Outlet key={user?.id || user?.username} />
}
