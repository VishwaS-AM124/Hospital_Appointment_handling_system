import { Link } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'

export default function NotFound() {
  const { user, homePath } = useAuth()
  return (
    <div className="auth">
      <div className="auth__card" style={{ textAlign: 'center' }}>
        <p className="auth__title">Page not found</p>
        <p className="auth__subtitle">
          That address does not match anything in this app.
        </p>
        <Link to={user ? homePath : '/login'}>
          {user ? 'Back to your dashboard' : 'Go to sign in'}
        </Link>
      </div>
    </div>
  )
}
