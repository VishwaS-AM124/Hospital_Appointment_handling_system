import { Navigate, useLocation } from 'react-router-dom'

import Spinner from '../components/Spinner'
import { useAuth } from './AuthContext'

/**
 * Route guard. Note this is convenience, not security — the API enforces every rule
 * independently. Hiding a button never stops a crafted request; the 403/404 from the
 * server is what actually protects the data.
 */
export default function ProtectedRoute({ role, children }) {
  const { user, loading, homePath } = useAuth()
  const location = useLocation()

  if (loading) return <Spinner label="Checking your session…" full />

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  if (role && user.role !== role) {
    // Signed in, wrong role: send them to their own home rather than a dead end.
    return <Navigate to={homePath} replace />
  }

  return children
}
