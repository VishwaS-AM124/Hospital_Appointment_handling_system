import { useCallback, useEffect, useMemo, useState } from 'react'

import * as api from '../../api/endpoints'
import Button from '../../components/Button'
import EmptyState from '../../components/EmptyState'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import PageHeader from '../../components/PageHeader'
import Pagination from '../../components/Pagination'
import Spinner from '../../components/Spinner'
import { useToast } from '../../components/Toast'
import {
  dateEndIso,
  dateStartIso,
  formatDuration,
  formatTime,
  groupByLocalDate,
  todayDateValue,
} from '../../utils/datetime'

export default function BrowseSlotsPage() {
  const toast = useToast()

  const [doctors, setDoctors] = useState([])
  const [services, setServices] = useState([])
  const [filters, setFilters] = useState({
    doctor_id: '',
    service_id: '',
    from: '',
    to: '',
  })
  const [page, setPage] = useState(1)
  const [slots, setSlots] = useState([])
  const [meta, setMeta] = useState({ page: 1, pages: 1, total: 0 })
  const [loading, setLoading] = useState(true)
  const [booking, setBooking] = useState(null)

  useEffect(() => {
    api.listDoctors().then(setDoctors).catch(() => setDoctors([]))
  }, [])

  // Service options only make sense once a doctor is chosen.
  useEffect(() => {
    if (!filters.doctor_id) {
      setServices([])
      return
    }
    api
      .listDoctorServices(filters.doctor_id)
      .then(setServices)
      .catch(() => setServices([]))
  }, [filters.doctor_id])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.listOpenSlots({
        doctor_id: filters.doctor_id || undefined,
        service_id: filters.service_id || undefined,
        date_from: dateStartIso(filters.from) || undefined,
        date_to: dateEndIso(filters.to) || undefined,
        page,
        page_size: 30,
      })
      setSlots(data.items)
      setMeta({ page: data.page, pages: data.pages, total: data.total })
    } catch (caught) {
      toast.error(caught.message)
    } finally {
      setLoading(false)
    }
  }, [filters, page, toast])

  useEffect(() => {
    load()
  }, [load])

  const grouped = useMemo(
    () => groupByLocalDate(slots, (slot) => slot.start_at),
    [slots],
  )

  const update = (key) => (event) => {
    const { value } = event.target
    setFilters((current) => ({
      ...current,
      [key]: value,
      // Changing doctor invalidates the service filter.
      ...(key === 'doctor_id' ? { service_id: '' } : {}),
    }))
    setPage(1)
  }

  return (
    <>
      <PageHeader
        title="Find an appointment"
        subtitle="Only slots that are still open and in the future are listed."
        actions={
          <Button variant="ghost" onClick={load}>
            Refresh
          </Button>
        }
      />

      <div className="panel">
        <div className="filter-bar">
          <Field
            as="select"
            label="Doctor"
            value={filters.doctor_id}
            onChange={update('doctor_id')}
          >
            <option value="">Any doctor</option>
            {doctors.map((doctor) => (
              <option key={doctor.id} value={doctor.id}>
                {doctor.full_name}
                {doctor.specialization ? ` · ${doctor.specialization}` : ''}
              </option>
            ))}
          </Field>
          <Field
            as="select"
            label="Service"
            value={filters.service_id}
            disabled={!filters.doctor_id || services.length === 0}
            onChange={update('service_id')}
          >
            <option value="">
              {filters.doctor_id ? 'Any service' : 'Choose a doctor first'}
            </option>
            {services.map((service) => (
              <option key={service.id} value={service.id}>
                {service.name}
              </option>
            ))}
          </Field>
          <Field
            label="From"
            type="date"
            min={todayDateValue()}
            value={filters.from}
            onChange={update('from')}
          />
          <Field
            label="To"
            type="date"
            min={filters.from || todayDateValue()}
            value={filters.to}
            onChange={update('to')}
          />
        </div>
      </div>

      {loading ? (
        <Spinner label="Finding open slots…" />
      ) : slots.length === 0 ? (
        <div className="card card--pad">
          <EmptyState title="No open slots match those filters" icon="🔍">
            Try widening the date range or choosing a different doctor.
          </EmptyState>
        </div>
      ) : (
        <>
          {grouped.map((group) => (
            <section className="day-group" key={group.key}>
              <h2 className="day-group__heading">{group.label}</h2>
              <div className="slot-list">
                {group.items.map((slot) => (
                  <article className="slot slot--open" key={slot.id}>
                    <div className="slot__time">
                      {formatTime(slot.start_at)} – {formatTime(slot.end_at)}
                      <small>{formatDuration(slot.duration_minutes)}</small>
                    </div>
                    <div className="slot__main">
                      <p className="slot__title">
                        {slot.doctor?.full_name || 'Doctor'}
                      </p>
                      <div className="slot__meta">
                        {slot.doctor?.specialization && (
                          <span>{slot.doctor.specialization}</span>
                        )}
                        <span>{slot.service ? slot.service.name : 'General appointment'}</span>
                        {slot.service && (
                          <span className="price">₹{slot.service.price.toFixed(2)}</span>
                        )}
                      </div>
                      {slot.notes && <p className="slot__note">{slot.notes}</p>}
                    </div>
                    <div className="slot__side">
                      {slot.waitlist_count > 0 && (
                        <span className="queue-chip" title="Patients waiting for this slot">
                          ⏳ {slot.waitlist_count} waiting
                        </span>
                      )}
                      <Button size="sm" onClick={() => setBooking(slot)}>
                        Book
                      </Button>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ))}
          <Pagination {...meta} onChange={setPage} />
        </>
      )}

      <BookModal
        slot={booking}
        onClose={() => setBooking(null)}
        onBooked={() => {
          setBooking(null)
          load()
        }}
        onLostRace={() => {
          setBooking(null)
          load()
        }}
      />
    </>
  )
}

function BookModal({ slot, onClose, onBooked, onLostRace }) {
  const toast = useToast()
  const [reason, setReason] = useState('')
  const [error, setError] = useState(null)
  const [pending, setPending] = useState(false)

  useEffect(() => {
    if (slot) {
      setReason('')
      setError(null)
    }
  }, [slot])

  async function confirm() {
    setError(null)
    setPending(true)
    try {
      await api.bookAppointment(slot.id, reason.trim() || null)
      toast.success('Booked. You can see it under My appointments.')
      onBooked()
    } catch (caught) {
      // Losing a booking race is an expected outcome, not a bug. The server has already
      // put this patient in the slot's queue and told us their position, so report that
      // rather than a bare failure.
      const queued = ['SLOT_ALREADY_BOOKED', 'SLOT_NOT_OPEN', 'SLOT_RESERVED'].includes(
        caught.code,
      )
      if (queued) {
        const position = caught.details?.position
        if (position) {
          toast.info(
            `Someone just took that slot — you are #${position} in the queue. ` +
              'We will notify you if it frees up.',
          )
        } else {
          toast.error('Someone just booked this slot. Refreshing the available times…')
        }
        onLostRace()
        return
      }
      setError(caught.message)
    } finally {
      setPending(false)
    }
  }

  return (
    <Modal
      open={Boolean(slot)}
      title="Confirm your appointment"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            Back
          </Button>
          <Button pending={pending} onClick={confirm}>
            {pending ? 'Booking…' : 'Confirm booking'}
          </Button>
        </>
      }
    >
      {slot && (
        <>
          {error && (
            <div className="form-error" role="alert">
              {error}
            </div>
          )}
          <div className="stack" style={{ marginBottom: '1rem' }}>
            <div className="row-between">
              <span className="muted small">Doctor</span>
              <strong>{slot.doctor?.full_name}</strong>
            </div>
            <div className="row-between">
              <span className="muted small">Service</span>
              <span>{slot.service ? slot.service.name : 'General appointment'}</span>
            </div>
            <div className="row-between">
              <span className="muted small">When</span>
              <span>
                {formatTime(slot.start_at)} – {formatTime(slot.end_at)}
              </span>
            </div>
            <div className="row-between">
              <span className="muted small">Length</span>
              <span>{formatDuration(slot.duration_minutes)}</span>
            </div>
            {slot.service && (
              <div className="row-between">
                <span className="muted small">Fee</span>
                <span className="price">₹{slot.service.price.toFixed(2)}</span>
              </div>
            )}
          </div>
          <Field
            as="textarea"
            rows={3}
            label="Reason for the visit (optional)"
            placeholder="Briefly describe your symptoms"
            maxLength={500}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </>
      )}
    </Modal>
  )
}
