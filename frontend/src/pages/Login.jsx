import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import Button from '../components/Button'
import Field from '../components/Field'
import Spinner from '../components/Spinner'

/** Seeded by backend/scripts/init_db.py — one click to sign in as either role. */
const DEMO_ACCOUNTS = [
  { label: 'Doctor', email: 'anita.rao@citycare-hospital.com', password: 'Passw0rd!' },
  { label: 'Patient', email: 'ravi.kumar@example.com', password: 'Passw0rd!' },
]

export default function Login() {
  const { login, user, loading, homePath } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [pending, setPending] = useState(false)

  if (loading) return <Spinner label="Loading…" full />
  if (user) return <Navigate to={location.state?.from || homePath} replace />

  async function submit(event) {
    event.preventDefault()
    setError(null)
    setPending(true)
    try {
      const signedIn = await login(email.trim(), password)
      navigate(signedIn.role === 'DOCTOR' ? '/doctor' : '/patient', { replace: true })
    } catch (caught) {
      setError(caught.message)
    } finally {
      setPending(false)
    }
  }

  function useDemo(account) {
    setEmail(account.email)
    setPassword(account.password)
    setError(null)
  }

  return (
    <div className="auth">
      <div className="auth__card">
        <div className="auth__brand">
          <span className="brand__mark" aria-hidden="true">
            ✚
          </span>
          <div>
            <p className="auth__title">CityCare</p>
            <p className="faint small">Appointment booking</p>
          </div>
        </div>

        <p className="auth__subtitle">Sign in to manage your appointments.</p>

        <form onSubmit={submit} noValidate>
          {error && (
            <div className="form-error" role="alert">
              {error}
            </div>
          )}

          <Field
            label="Email"
            type="email"
            name="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <Field
            label="Password"
            type="password"
            name="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />

          <Button type="submit" size="lg" pending={pending}>
            {pending ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>

        <div className="demo">
          <p className="demo__title">Demo accounts (password Passw0rd!)</p>
          <div className="demo__row">
            {DEMO_ACCOUNTS.map((account) => (
              <Button
                key={account.email}
                variant="secondary"
                size="sm"
                onClick={() => useDemo(account)}
              >
                Fill {account.label}
              </Button>
            ))}
          </div>
          <p className="faint small" style={{ marginTop: '0.5rem' }}>
            Run <code>python -m scripts.init_db</code> to create them.
          </p>
        </div>

        <p className="auth__footer">
          No account yet? <Link to="/register">Create one</Link>
        </p>
      </div>
    </div>
  )
}
