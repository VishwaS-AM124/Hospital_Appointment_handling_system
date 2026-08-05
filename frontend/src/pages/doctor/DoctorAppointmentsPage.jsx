import { useCallback, useEffect, useState } from 'react'

import * as api from '../../api/endpoints'
import Button from '../../components/Button'
import ConfirmDialog from '../../components/ConfirmDialog'
import EmptyState from '../../components/EmptyState'
import PageHeader from '../../components/PageHeader'
import Pagination from '../../components/Pagination'
import Spinner from '../../components/Spinner'
import StatusBadge from '../../components/StatusBadge'
import Tabs from '../../components/Tabs'
import { useToast } from '../../components/Toast'
import { formatRange, isPast, relativeTime } from '../../utils/datetime'

const TABS = [
  { value: 'upcoming', label: 'Upcoming' },
  { value: 'past', label: 'Past' },
  { value: 'all', label: 'All' },
]

export default function DoctorAppointmentsPage() {
  const toast = useToast()

  const [scope, setScope] = useState('upcoming')
  const [page, setPage] = useState(1)
  const [items, setItems] = useState([])
  const [meta, setMeta] = useState({ page: 1, pages: 1, total: 0 })
  const [loading, setLoading] = useState(true)
  const [cancelling, setCancelling] = useState(null)
  const [completing, setCompleting] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.listDoctorAppointments({ scope, page, page_size: 25 })
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
      toast.success('Appointment cancelled — the slot is open again.')
      setCancelling(null)
      load()
    } catch (caught) {
      toast.error(caught.message)
    } finally {
      setBusy(false)
    }
  }

  async function complete(notes) {
    setBusy(true)
    try {
      await api.completeAppointment(completing.id, notes)
      toast.success('Marked as completed.')
      setCompleting(null)
      load()
    } catch (caught) {
      toast.error(caught.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader
        title="Appointments"
        subtitle="Only your own schedule is ever shown here."
      />

      <Tabs
        value={scope}
        options={TABS}
        onChange={(value) => {
          setScope(value)
          setPage(1)
        }}
      />

      {loading ? (
        <Spinner label="Loading appointments…" />
      ) : items.length === 0 ? (
        <div className="card card--pad">
          <EmptyState title="Nothing here yet" icon="🩺">
            {scope === 'upcoming'
              ? 'No upcoming appointments. Publish availability so patients can book.'
              : 'No appointments in this view.'}
          </EmptyState>
        </div>
      ) : (
        <>
          <div className="card table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Patient</th>
                  <th>Reason</th>
                  <th>Status</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {items.map((appointment) => {
                  const started = isPast(appointment.slot?.start_at)
                  const active = appointment.status === 'BOOKED'
                  return (
                    <tr key={appointment.id}>
                      <td>
                        {formatRange(
                          appointment.slot?.start_at,
                          appointment.slot?.end_at,
                        )}
                        <div className="faint small">
                          {relativeTime(appointment.slot?.start_at)}
                          {appointment.slot?.service
                            ? ` · ${appointment.slot.service.name}`
                            : ''}
                        </div>
                      </td>
                      <td>
                        {appointment.patient?.full_name || '—'}
                        {appointment.patient?.phone && (
                          <div className="faint small">{appointment.patient.phone}</div>
                        )}
                      </td>
                      <td className="muted small">
                        {appointment.reason || '—'}
                        {appointment.doctor_notes && (
                          <div className="faint small">
                            Notes: {appointment.doctor_notes}
                          </div>
                        )}
                        {appointment.cancel_reason && (
                          <div className="faint small">
                            Cancelled ({appointment.cancelled_by?.toLowerCase()}):{' '}
                            {appointment.cancel_reason}
                          </div>
                        )}
                      </td>
                      <td>
                        <StatusBadge status={appointment.status} />
                      </td>
                      <td>
                        <div className="btn-row">
                          {active && (
                            <span
                              className="tip"
                              title={
                                started
                                  ? undefined
                                  : 'You can mark this completed once the appointment time has started.'
                              }
                            >
                              <Button
                                variant="success"
                                size="sm"
                                disabled={!started}
                                onClick={() => setCompleting(appointment)}
                              >
                                Complete
                              </Button>
                            </span>
                          )}
                          {active && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setCancelling(appointment)}
                            >
                              Cancel
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <Pagination {...meta} onChange={setPage} />
        </>
      )}

      <ConfirmDialog
        open={Boolean(cancelling)}
        title="Cancel this appointment?"
        message={
          cancelling
            ? `${cancelling.patient?.full_name} · ${formatRange(
                cancelling.slot?.start_at,
                cancelling.slot?.end_at,
              )}. The slot will reopen for booking.`
            : ''
        }
        confirmLabel="Cancel appointment"
        noteLabel="Reason (optional)"
        notePlaceholder="Called into surgery / patient did not attend"
        pending={busy}
        onConfirm={cancel}
        onClose={() => setCancelling(null)}
      />

      <ConfirmDialog
        open={Boolean(completing)}
        title="Mark as completed?"
        message={
          completing
            ? `${completing.patient?.full_name} · ${formatRange(
                completing.slot?.start_at,
                completing.slot?.end_at,
              )}.`
            : ''
        }
        confirmLabel="Mark completed"
        variant="success"
        noteLabel="Consultation notes (optional)"
        notePlaceholder="Diagnosis, prescription, follow-up…"
        pending={busy}
        onConfirm={complete}
        onClose={() => setCompleting(null)}
      />
    </>
  )
}
