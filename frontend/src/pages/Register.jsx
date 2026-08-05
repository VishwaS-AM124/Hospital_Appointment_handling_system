import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import Button from '../components/Button'
import Field from '../components/Field'
import Spinner from '../components/Spinner'

export default function Register() {
  const { register, user, loading, homePath } = useAuth()
  const navigate = useNavigate()

  const [role, setRole] = useState('PATIENT')
  const [form, setForm] = useState({
    full_name: '',
    email: '',
    password: '',
    phone: '',
    specialization: '',
  })
  const [error, setError] = useState(null)
  const [fieldErrors, setFieldErrors] = useState({})
  const [pending, setPending] = useState(false)

  if (loading) return <Spinner label="Loading…" full />
  if (user) return <Navigate to={homePath} replace />

  const update = (key) => (event) =>
    setForm((current) => ({ ...current, [key]: event.target.value }))

  async function submit(event) {
    event.preventDefault()
    setError(null)
    setFieldErrors({})
    setPending(true)

    const payload = {
      full_name: form.full_name.trim(),
      email: form.email.trim(),
      password: form.password,
      role,
      phone: form.phone.trim() || null,
      // The API rejects a specialization on a patient account, so only send it for
      // doctors rather than relying on the server to ignore it.
      specialization:
        role === 'DOCTOR' ? form.specialization.trim() || null : null,
    }

    try {
      const created = await register(payload)
      navigate(created.role === 'DOCTOR' ? '/doctor' : '/patient', { replace: true })
    } catch (caught) {
      setError(caught.message)
      if (Array.isArray(caught.details)) {
        const mapped = {}
        for (const detail of caught.details) {
          const key = String(detail.field || '').split('.').pop()
          if (key) mapped[key] = detail.message
        }
        setFieldErrors(mapped)
      }
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="auth">
      <div className="auth__card">
        <div className="auth__brand">
          <span className="brand__mark" aria-hidden="true">
            ✚
          </span>
          <div>
            <p className="auth__title">Create an account</p>
            <p className="faint small">CityCare appointment booking</p>
          </div>
        </div>

        <form onSubmit={submit} noValidate>
          {error && (
            <div className="form-error" role="alert">
              {error}
            </div>
          )}

          <div className="role-toggle" role="group" aria-label="Account type">
            {['PATIENT', 'DOCTOR'].map((option) => (
              <button
                key={option}
                type="button"
                className={
                  role === option ? 'role-option role-option--active' : 'role-option'
                }
                aria-pressed={role === option}
                onClick={() => setRole(option)}
              >
                {option === 'PATIENT' ? "I'm a patient" : "I'm a doctor"}
              </button>
            ))}
          </div>

          <Field
            label="Full name"
            required
            value={form.full_name}
            error={fieldErrors.full_name}
            onChange={update('full_name')}
          />
          <Field
            label="Email"
            type="email"
            autoComplete="username"
            required
            value={form.email}
            error={fieldErrors.email}
            onChange={update('email')}
          />
          <Field
            label="Password"
            type="password"
            autoComplete="new-password"
            required
            value={form.password}
            hint="At least 8 characters, including a letter and a digit."
            error={fieldErrors.password}
            onChange={update('password')}
          />
          <Field
            label="Phone (optional)"
            value={form.phone}
            error={fieldErrors.phone}
            onChange={update('phone')}
          />
          {role === 'DOCTOR' && (
            <Field
              label="Specialization"
              placeholder="e.g. Cardiology"
              value={form.specialization}
              error={fieldErrors.specialization}
              onChange={update('specialization')}
            />
          )}

          <Button type="submit" size="lg" pending={pending}>
            {pending ? 'Creating account…' : 'Create account'}
          </Button>
        </form>

        <p className="auth__footer">
          Already registered? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  )
}
