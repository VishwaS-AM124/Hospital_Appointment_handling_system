import { useCallback, useEffect, useMemo, useState } from 'react'

import * as api from '../../api/endpoints'
import Button from '../../components/Button'
import ConfirmDialog from '../../components/ConfirmDialog'
import EmptyState from '../../components/EmptyState'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import PageHeader from '../../components/PageHeader'
import Pagination from '../../components/Pagination'
import Spinner from '../../components/Spinner'
import StatusBadge from '../../components/StatusBadge'
import { useToast } from '../../components/Toast'
import {
  formatDuration,
  formatTime,
  groupByLocalDate,
  toIsoUtc,
  toLocalInputValue,
  todayDateValue,
  tzOffsetMinutes,
} from '../../utils/datetime'

const STATUS_FILTERS = [
  { value: '', label: 'All statuses' },
  { value: 'OPEN', label: 'Open' },
  { value: 'BOOKED', label: 'Booked' },
  { value: 'COMPLETED', label: 'Completed' },
]

/** Rule 4: only an OPEN slot may be edited or deleted. */
function isEditable(slot) {
  return slot.status === 'OPEN'
}

const LOCKED_REASON =
  'This slot has an appointment on it. Cancel the appointment first to edit or delete it.'

export default function SlotsPage() {
  const toast = useToast()

  const [slots, setSlots] = useState([])
  const [meta, setMeta] = useState({ page: 1, pages: 1, total: 0 })
  const [services, setServices] = useState([])
  const [statusFilter, setStatusFilter] = useState('')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)

  const [singleOpen, setSingleOpen] = useState(false)
  const [bulkOpen, setBulkOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.listMySlots({
        status: statusFilter || undefined,
        page,
        page_size: 50,
      })
      setSlots(data.items)
      setMeta({ page: data.page, pages: data.pages, total: data.total })
    } catch (caught) {
      toast.error(caught.message)
    } finally {
      setLoading(false)
    }
  }, [statusFilter, page, toast])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    api.listMyServices().then(setServices).catch(() => setServices([]))
  }, [])

  const grouped = useMemo(
    () => groupByLocalDate(slots, (slot) => slot.start_at),
    [slots],
  )

  async function removeSlot() {
    setBusy(true)
    try {
      await api.deleteSlot(deleting.id)
      toast.success('Slot deleted.')
      setDeleting(null)
      load()
    } catch (caught) {
      // Someone may have booked it a moment ago — refresh so the UI catches up.
      toast.error(caught.message)
      if (caught.code === 'SLOT_HAS_APPOINTMENT') {
        setDeleting(null)
        load()
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader
        title="Availability"
        subtitle="Publish the windows patients can book. A booked slot is locked until the appointment is cancelled."
        actions={
          <>
            <Button variant="secondary" onClick={() => setBulkOpen(true)}>
              Generate a day
            </Button>
            <Button onClick={() => setSingleOpen(true)}>New slot</Button>
          </>
        }
      />

      <div className="panel">
        <div className="filter-bar">
          <Field
            as="select"
            label="Status"
            value={statusFilter}
            onChange={(event) => {
              setStatusFilter(event.target.value)
              setPage(1)
            }}
          >
            {STATUS_FILTERS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Field>
          <div style={{ flex: 2 }} />
          <Button variant="ghost" size="sm" onClick={load}>
            Refresh
          </Button>
        </div>
      </div>

      {loading ? (
        <Spinner label="Loading your schedule…" />
      ) : slots.length === 0 ? (
        <div className="card card--pad">
          <EmptyState title="No slots yet">
            Publish your first availability window with <strong>New slot</strong>, or
            generate a whole working day at once.
          </EmptyState>
        </div>
      ) : (
        <>
          {grouped.map((group) => (
            <section className="day-group" key={group.key}>
              <h2 className="day-group__heading">{group.label}</h2>
              <div className="slot-list">
                {group.items.map((slot) => {
                  const editable = isEditable(slot)
                  return (
                    <article
                      className={`slot slot--${slot.status.toLowerCase()}`}
                      key={slot.id}
                    >
                      <div className="slot__time">
                        {formatTime(slot.start_at)} – {formatTime(slot.end_at)}
                        <small>{formatDuration(slot.duration_minutes)}</small>
                      </div>

                      <div className="slot__main">
                        <p className="slot__title">
                          {slot.service ? slot.service.name : 'General appointment'}
                        </p>
                        <div className="slot__meta">
                          <StatusBadge status={slot.status} />
                          {slot.appointment?.patient && (
                            <span>
                              {slot.appointment.patient.full_name}
                              {slot.appointment.patient.phone
                                ? ` · ${slot.appointment.patient.phone}`
                                : ''}
                            </span>
                          )}
                          {slot.waitlist_count > 0 && (
                            <span
                              className="queue-chip"
                              title="Patients queued for this slot. If you cancel, the first in line is notified automatically."
                            >
                              ⏳ {slot.waitlist_count} waiting
                            </span>
                          )}
                        </div>
                        {slot.appointment?.reason && (
                          <p className="slot__note">“{slot.appointment.reason}”</p>
                        )}
                        {slot.notes && <p className="slot__note">{slot.notes}</p>}
                      </div>

                      <div className="slot__side">
                        {/* A disabled button eats hover events, so the tooltip goes on
                            the wrapper — the reason stays discoverable. */}
                        <span
                          className="tip"
                          title={editable ? undefined : LOCKED_REASON}
                        >
                          <Button
                            variant="secondary"
                            size="sm"
                            disabled={!editable}
                            onClick={() => setEditing(slot)}
                          >
                            Edit
                          </Button>
                        </span>
                        <span
                          className="tip"
                          title={editable ? undefined : LOCKED_REASON}
                        >
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={!editable}
                            onClick={() => setDeleting(slot)}
                          >
                            Delete
                          </Button>
                        </span>
                      </div>
                    </article>
                  )
                })}
              </div>
            </section>
          ))}
          <Pagination {...meta} onChange={setPage} />
        </>
      )}

      <SlotFormModal
        open={singleOpen}
        services={services}
        onClose={() => setSingleOpen(false)}
        onSaved={() => {
          setSingleOpen(false)
          load()
        }}
      />

      <SlotFormModal
        open={Boolean(editing)}
        slot={editing}
        services={services}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null)
          load()
        }}
      />

      <BulkModal
        open={bulkOpen}
        services={services}
        onClose={() => setBulkOpen(false)}
        onSaved={() => {
          setBulkOpen(false)
          load()
        }}
      />

      <ConfirmDialog
        open={Boolean(deleting)}
        title="Delete this slot?"
        message={
          deleting
            ? `${formatTime(deleting.start_at)} – ${formatTime(
                deleting.end_at,
              )} will be removed from your schedule.`
            : ''
        }
        confirmLabel="Delete slot"
        pending={busy}
        onConfirm={removeSlot}
        onClose={() => setDeleting(null)}
      />
    </>
  )
}

/* ------------------------------------------------------------------ create / edit */

function SlotFormModal({ open, slot, services, onClose, onSaved }) {
  const toast = useToast()
  const editMode = Boolean(slot)

  const [startLocal, setStartLocal] = useState('')
  const [endLocal, setEndLocal] = useState('')
  const [serviceId, setServiceId] = useState('')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState(null)
  const [pending, setPending] = useState(false)

  useEffect(() => {
    if (!open) return
    setError(null)
    setStartLocal(slot ? toLocalInputValue(slot.start_at) : '')
    setEndLocal(slot ? toLocalInputValue(slot.end_at) : '')
    setServiceId(slot?.service_id ? String(slot.service_id) : '')
    setNotes(slot?.notes || '')
  }, [open, slot])

  /** Picking a service pre-fills the end time from its duration. */
  function chooseService(value) {
    setServiceId(value)
    const service = services.find((item) => String(item.id) === value)
    if (service && startLocal) {
      const end = new Date(startLocal)
      end.setMinutes(end.getMinutes() + service.duration_minutes)
      setEndLocal(toLocalInputValue(end.toISOString()))
    }
  }

  async function submit(event) {
    event.preventDefault()
    setError(null)
    setPending(true)

    const startIso = toIsoUtc(startLocal)
    const endIso = toIsoUtc(endLocal)
    if (!startIso || !endIso) {
      setError('Please provide both a start and an end time.')
      setPending(false)
      return
    }

    try {
      if (editMode) {
        await api.updateSlot(slot.id, {
          start_at: startIso,
          end_at: endIso,
          notes: notes.trim() || null,
          service_id: serviceId ? Number(serviceId) : null,
          clear_service: !serviceId,
        })
        toast.success('Slot updated.')
      } else {
        await api.createSlot({
          start_at: startIso,
          end_at: endIso,
          notes: notes.trim() || null,
          service_id: serviceId ? Number(serviceId) : null,
        })
        toast.success('Slot published.')
      }
      onSaved()
    } catch (caught) {
      setError(caught.message)
    } finally {
      setPending(false)
    }
  }

  return (
    <Modal
      open={open}
      title={editMode ? 'Edit slot' : 'New slot'}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button form="slot-form" type="submit" pending={pending}>
            {editMode ? 'Save changes' : 'Publish slot'}
          </Button>
        </>
      }
    >
      <form id="slot-form" onSubmit={submit} noValidate>
        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}
        <Field
          as="select"
          label="Service (optional)"
          value={serviceId}
          onChange={(event) => chooseService(event.target.value)}
        >
          <option value="">General appointment</option>
          {services
            .filter((service) => service.is_active || String(service.id) === serviceId)
            .map((service) => (
              <option key={service.id} value={service.id}>
                {service.name} · {formatDuration(service.duration_minutes)}
              </option>
            ))}
        </Field>
        <Field
          label="Starts"
          type="datetime-local"
          required
          value={startLocal}
          hint="Shown in your local time; stored as UTC."
          onChange={(event) => setStartLocal(event.target.value)}
        />
        <Field
          label="Ends"
          type="datetime-local"
          required
          value={endLocal}
          onChange={(event) => setEndLocal(event.target.value)}
        />
        <Field
          as="textarea"
          rows={2}
          label="Notes for the patient (optional)"
          maxLength={500}
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
        />
      </form>
    </Modal>
  )
}

/* --------------------------------------------------------------------- bulk create */

function BulkModal({ open, services, onClose, onSaved }) {
  const toast = useToast()
  const [form, setForm] = useState({
    date: '',
    start_time: '09:00',
    end_time: '13:00',
    slot_minutes: 30,
    gap_minutes: 0,
    service_id: '',
  })
  const [error, setError] = useState(null)
  const [pending, setPending] = useState(false)

  useEffect(() => {
    if (open) setError(null)
  }, [open])

  const update = (key) => (event) =>
    setForm((current) => ({ ...current, [key]: event.target.value }))

  async function submit(event) {
    event.preventDefault()
    setError(null)
    setPending(true)
    try {
      const result = await api.bulkCreateSlots({
        date: form.date,
        start_time: form.start_time,
        end_time: form.end_time,
        slot_minutes: Number(form.slot_minutes),
        gap_minutes: Number(form.gap_minutes),
        service_id: form.service_id ? Number(form.service_id) : null,
        // The server works in UTC; send our offset so "09:00" means 09:00 here.
        tz_offset_minutes: tzOffsetMinutes(),
      })
      const created = result.created.length
      const skipped = result.skipped.length
      if (created === 0) {
        toast.info(
          skipped > 0
            ? `Nothing created — all ${skipped} slot(s) clashed with your existing schedule.`
            : 'Nothing created — check the time window.',
        )
      } else {
        toast.success(
          `Created ${created} slot(s)${skipped ? `, skipped ${skipped} clash(es).` : '.'}`,
        )
      }
      onSaved()
    } catch (caught) {
      setError(caught.message)
    } finally {
      setPending(false)
    }
  }

  return (
    <Modal
      open={open}
      title="Generate a day of slots"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button form="bulk-form" type="submit" pending={pending}>
            Generate
          </Button>
        </>
      }
    >
      <form id="bulk-form" onSubmit={submit} noValidate>
        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}
        <p className="dialog-message">
          Fills the window with back-to-back slots. Anything clashing with your existing
          schedule is skipped and reported, not rejected.
        </p>
        <Field
          label="Date"
          type="date"
          required
          min={todayDateValue()}
          value={form.date}
          onChange={update('date')}
        />
        <div className="form-grid">
          <Field
            label="From"
            type="time"
            required
            value={form.start_time}
            onChange={update('start_time')}
          />
          <Field
            label="To"
            type="time"
            required
            value={form.end_time}
            onChange={update('end_time')}
          />
          <Field
            label="Slot length (min)"
            type="number"
            min={5}
            max={480}
            required
            value={form.slot_minutes}
            onChange={update('slot_minutes')}
          />
          <Field
            label="Gap between (min)"
            type="number"
            min={0}
            max={240}
            value={form.gap_minutes}
            onChange={update('gap_minutes')}
          />
        </div>
        <Field
          as="select"
          label="Service (optional)"
          value={form.service_id}
          onChange={update('service_id')}
        >
          <option value="">General appointment</option>
          {services
            .filter((service) => service.is_active)
            .map((service) => (
              <option key={service.id} value={service.id}>
                {service.name}
              </option>
            ))}
        </Field>
      </form>
    </Modal>
  )
}
