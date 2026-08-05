import { Link, NavLink } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import Button from './Button'
import NotificationBell from './NotificationBell'

const DOCTOR_NAV = [
  { to: '/doctor', label: 'Overview', end: true },
  { to: '/doctor/slots', label: 'Availability' },
  { to: '/doctor/appointments', label: 'Appointments' },
  { to: '/doctor/services', label: 'Services' },
]

const PATIENT_NAV = [
  { to: '/patient', label: 'Find a slot', end: true },
  { to: '/patient/appointments', label: 'My appointments' },
]

export default function Layout({ children }) {
  const { user, logout, isDoctor, homePath } = useAuth()
  const links = isDoctor ? DOCTOR_NAV : PATIENT_NAV

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar__inner">
          <Link to={homePath} className="brand">
            <span className="brand__mark" aria-hidden="true">
              ✚
            </span>
            <span className="brand__text">
              CityCare
              <small>Appointment Booking</small>
            </span>
          </Link>

          <nav className="nav" aria-label="Main navigation">
            {links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.end}
                className={({ isActive }) =>
                  isActive ? 'nav__link nav__link--active' : 'nav__link'
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>

          <div className="topbar__user">
            <NotificationBell />
            <div className="whoami">
              <span className="whoami__name">{user.full_name}</span>
              <span className="whoami__role">
                {isDoctor ? user.specialization || 'Doctor' : 'Patient'}
              </span>
            </div>
            <Button variant="ghost" size="sm" onClick={logout}>
              Sign out
            </Button>
          </div>
        </div>
      </header>

      <main className="content">{children}</main>

      <footer className="footer">
        <span>
          Double-booking is prevented by a row lock, a status re-check and a unique
          index — see <code>docs/DESIGN.md</code>.
        </span>
      </footer>
    </div>
  )
}
