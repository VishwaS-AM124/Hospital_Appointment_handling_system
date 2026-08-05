import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import * as api from '../../api/endpoints'
import Button from '../../components/Button'
import ConfirmDialog from '../../components/ConfirmDialog'
import EmptyState from '../../components/EmptyState'
import PageHeader from '../../components/PageHeader'
import Pagination from '../../components/Pagination'
import Spinner from '../../components/Spinner'
import StatusBadge from '../../components/StatusBadge'
import { useToast } from '../../components/Toast'
import { formatRange, isPast, relativeTime } from '../../utils/datetime'
import Tabs from '../../components/Tabs'
import WaitlistPanel from '../../components/WaitlistPanel'

const TABS = [
  { value: 'upcoming', label: 'Upcoming' },
  { value: 'past', label: 'Past' },
  { value: 'all', label: 'All' },
  { value: 'waiting', label: 'Waiting list' },
]

export default function MyAppointmentsPage() {
  const toast = useToast()
  const [scope, setScope] = useState('upcoming')
  const [page, setPage] = useState(1)
  const [items, setItems] = useState([])
  const [meta, setMeta] = useState({ page: 1, pages: 1, total: 0 })
  const [loading, setLoading] = useState(true)
  const [cancelling, setCancelling] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    // The waiting-list tab is served by WaitlistPanel, which loads its own data.
    if (scope === 'waiting') {
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const data = await api.listMyAppointments({ scope, page, page_size: 25 })
      setItems(data.items)
      setMeta({ page: data.page, pages: data.pages, total: data.total })
    } catch (caught) {
      toast.error(caught.message)
    } finally {
      setLoading(false)
    }
  }, [scope, page, toast])

  useEffect(() => {
    load()
  }, [load])

  async function cancel(reason) {
    setBusy(true)
    try {
      await api.cancelAppointment(cancelling.id, reason)
      toast.success('Cancelled. The slot is now open for someone else.')
      setCancelling(null)
      load()
    } catch (caught) {
      toast.error(caught.message)
      if (caught.code === 'CANCEL_WINDOW_CLOSED') {
        setCancelling(null)
        load()
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader
        title="My appointments"
        subtitle="Only your own bookings appear here."
        actions={
          <Link to="/patient">
            <Button variant="secondary">Book another</Button>
          </Link>
        }
      />

      <Tabs
        value={scope}
        options={TABS}
        onChange={(value) => {
          setScope(value)
          setPage(1)
        }}
      />

      {scope === 'waiting' ? (
        <>
          <div className="notice">
            When a slot you wanted is taken, you join its queue automatically. If it is
            released, whoever is first in line is notified and gets an exclusive window to
            book it before anyone else.
          </div>
          <WaitlistPanel onBooked={() => setScope('upcoming')} />
        </>
      ) : loading ? (
        <Spinner label="Loading your appointments…" />
      ) : items.length === 0 ? (
        <div className="card card--pad">
          <EmptyState title="Nothing booked" icon="📅">
            <Link to="/patient">Browse open slots</Link> to book your first appointment.
          </EmptyState>
        </div>
      ) : (
        <>
          <div className="slot-list">
            {items.map((appointment) => {
              const started = isPast(appointment.slot?.start_at)
              const canCancel = appointment.status === 'BOOKED' && !started
              return (
                <article
                  className={`slot slot--${appointment.status.toLowerCase()}`}
                  key={appointment.id}
                >
                  <div className="slot__time">
                    {formatRange(appointment.slot?.start_at, appointment.slot?.end_at)}
                    <small>{relativeTime(appointment.slot?.start_at)}</small>
                  </div>

                  <div className="slot__main">
                    <p className="slot__title">
                      {appointment.doctor?.full_name || 'Doctor'}
                    </p>
                    <div className="slot__meta">
                      <StatusBadge status={appointment.status} />
                      {appointment.doctor?.specialization && (
                        <span>{appointment.doctor.specialization}</span>
                      )}
                      {appointment.slot?.service && (
                        <span>{appointment.slot.service.name}</span>
                      )}
                    </div>
                    {appointment.reason && (
                      <p className="slot__note">“{appointment.reason}”</p>
                    )}
                    {appointment.doctor_notes && (
                      <p className="slot__note">
                        Doctor’s notes: {appointment.doctor_notes}
                      </p>
                    )}
                    {appointment.cancel_reason && (
                      <p className="slot__note">
                        Cancelled by {appointment.cancelled_by?.toLowerCase()}:{' '}
                        {appointment.cancel_reason}
                      </p>
                    )}
                  </div>

                  <div className="slot__side">
                    {appointment.status === 'BOOKED' && (
                      <span
                        className="tip"
                        title={
                          canCancel
                            ? undefined
                            : 'This appointment has already started — please contact the clinic.'
                        }
                      >
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={!canCancel}
                          onClick={() => setCancelling(appointment)}
                        >
                          Cancel
                        </Button>
                      </span>
                    )}
                  </div>
                </article>
              )
            })}
          </div>
          <Pagination {...meta} onChange={setPage} />
        </>
      )}

      <ConfirmDialog
        open={Boolean(cancelling)}
        title="Cancel this appointment?"
        message={
          cancelling
            ? `${cancelling.doctor?.full_name} · ${formatRange(
                cancelling.slot?.start_at,
                cancelling.slot?.end_at,
              )}. The slot will become available to other patients.`
            : ''
        }
        confirmLabel="Cancel appointment"
        noteLabel="Reason (optional)"
        notePlaceholder="Work conflict, feeling better…"
        pending={busy}
        onConfirm={cancel}
        onClose={() => setCancelling(null)}
      />
    </>
  )
}
