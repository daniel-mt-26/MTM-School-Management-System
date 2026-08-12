import { useContext } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { AuthContext } from './context'
import { routeForRole } from './roleRoutes'

export default function ProtectedRoute({ allowedRole }) {
  const { user, isLoading } = useContext(AuthContext)
  const location = useLocation()

  if (isLoading) return <main className="loading-screen">Checking your session…</main>
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />
  if (allowedRole && user.role !== allowedRole) return <Navigate to={routeForRole(user.role)} replace />
  return <Outlet />
}
