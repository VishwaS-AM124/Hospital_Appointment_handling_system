import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import * as api from '../../api/endpoints'
import { useAuth } from '../../auth/AuthContext'
import EmptyState from '../../components/EmptyState'
import PageHeader from '../../components/PageHeader'
import Spinner from '../../components/Spinner'
import StatusBadge from '../../components/StatusBadge'
import { useToast } from '../../components/Toast'
import { formatRange, relativeTime } from '../../utils/datetime'

export default function DoctorHome() {
  const { user } = useAuth()
  const toast = useToast()
  const [stats, setStats] = useState(null)
  const [next, setNext] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const [open, booked, upcoming, services] = await Promise.all([
          api.listMySlots({ status: 'OPEN', page_size: 1 }),
          api.listMySlots({ status: 'BOOKED', page_size: 1 }),
          api.listDoctorAppointments({ scope: 'upcoming', status: 'BOOKED', page_size: 5 }),
          api.listMyServices(),
        ])
        if (cancelled) return
        setStats({
          open: open.total,
          booked: booked.total,
          upcoming: upcoming.total,
          services: services.length,
        })
        setNext(upcoming.items)
      } catch (caught) {
        if (!cancelled) toast.error(caught.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [toast])

  if (loading) return <Spinner label="Loading your overview…" full />

  return (
    <>
      <PageHeader
        title={`Welcome, ${user.full_name}`}
        subtitle={user.specialization || 'Doctor'}
      />

      <div className="stat-grid">
        <div className="stat">
          <p className="stat__value">{stats?.open ?? 0}</p>
          <p className="stat__label">Open slots</p>
        </div>
        <div className="stat">
          <p className="stat__value">{stats?.booked ?? 0}</p>
          <p className="stat__label">Booked slots</p>
        </div>
        <div className="stat">
          <p className="stat__value">{stats?.upcoming ?? 0}</p>
          <p className="stat__label">Upcoming appointments</p>
        </div>
        <div className="stat">
          <p className="stat__value">{stats?.services ?? 0}</p>
          <p className="stat__label">Services offered</p>
        </div>
      </div>

      <div className="panel">
        <h2 className="panel__title">Next appointments</h2>
        {next.length === 0 ? (
          <EmptyState title="Nothing booked yet" icon="🩺">
            Publish availability on the <Link to="/doctor/slots">Availability</Link> page
            and patients can start booking.
          </EmptyState>
        ) : (
          <div className="slot-list">
            {next.map((appointment) => (
              <article className="slot slot--booked" key={appointment.id}>
                <div className="slot__time">
                  {formatRange(appointment.slot?.start_at, appointment.slot?.end_at)}
                  <small>{relativeTime(appointment.slot?.start_at)}</small>
                </div>
                <div className="slot__main">
                  <p className="slot__title">{appointment.patient?.full_name}</p>
                  <div className="slot__meta">
                    <StatusBadge status={appointment.status} />
                    {appointment.slot?.service && (
                      <span>{appointment.slot.service.name}</span>
                    )}
                    {appointment.patient?.phone && (
                      <span>{appointment.patient.phone}</span>
                    )}
                  </div>
                  {appointment.reason && (
                    <p className="slot__note">“{appointment.reason}”</p>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
      </div>

      <div className="panel">
        <h2 className="panel__title">How this system protects your schedule</h2>
        <ul className="muted small" style={{ margin: 0, paddingLeft: '1.1rem' }}>
          <li>
            A slot can hold only one live appointment. Simultaneous bookings are
            serialized by a row lock and backstopped by a unique database index.
          </li>
          <li>
            A booked slot cannot be edited or deleted until the appointment is cancelled.
          </li>
          <li>Cancelling an appointment reopens the slot automatically.</li>
          <li>No other doctor can see or modify your schedule.</li>
        </ul>
      </div>
    </>
  )
}
