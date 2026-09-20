import { useContext } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { AuthContext } from './context'
import { routeForRole } from './roleRoutes'

export default function ProtectedRoute({ allowedRole }) {
  const { user, isLoading, accessBlocked } = useContext(AuthContext)
  const location = useLocation()

  if (isLoading) return <main className="loading-screen">Checking your session…</main>
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />
  if (accessBlocked && location.pathname !== '/school-access-blocked') return <Navigate to="/school-access-blocked" replace />
  if (user.must_change_password && location.pathname !== '/change-password') return <Navigate to="/change-password" replace />
  if (allowedRole && user.role !== allowedRole) return <Navigate to={routeForRole(user.role)} replace />
  return <Outlet />
}
