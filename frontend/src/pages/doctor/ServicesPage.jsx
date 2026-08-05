import { useCallback, useEffect, useState } from 'react'

import * as api from '../../api/endpoints'
import Button from '../../components/Button'
import ConfirmDialog from '../../components/ConfirmDialog'
import EmptyState from '../../components/EmptyState'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import PageHeader from '../../components/PageHeader'
import Spinner from '../../components/Spinner'
import { useToast } from '../../components/Toast'
import { formatDuration } from '../../utils/datetime'

export default function ServicesPage() {
  const toast = useToast()
  const [services, setServices] = useState([])
  const [loading, setLoading] = useState(true)
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setServices(await api.listMyServices())
    } catch (caught) {
      toast.error(caught.message)
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => {
    load()
  }, [load])

  async function toggleActive(service) {
    try {
      await api.updateService(service.id, { is_active: !service.is_active })
      toast.success(
        service.is_active
          ? `${service.name} is no longer offered.`
          : `${service.name} is offered again.`,
      )
      load()
    } catch (caught) {
      toast.error(caught.message)
    }
  }

  async function remove() {
    setBusy(true)
    try {
      await api.deleteService(deleting.id)
      toast.success('Service deleted.')
      setDeleting(null)
      load()
    } catch (caught) {
      toast.error(caught.message)
      if (caught.code === 'SERVICE_IN_USE') setDeleting(null)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader
        title="Services"
        subtitle="What you offer. Slots can be labelled with a service so patients know what they are booking."
        actions={<Button onClick={() => setFormOpen(true)}>New service</Button>}
      />

      {loading ? (
        <Spinner label="Loading services…" />
      ) : services.length === 0 ? (
        <div className="card card--pad">
          <EmptyState title="No services yet" icon="💉">
            Add one so your availability can be labelled — for example “Cardiology
            Consultation, 30 min”.
          </EmptyState>
        </div>
      ) : (
        <div className="card table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Service</th>
                <th>Duration</th>
                <th>Price</th>
                <th>Offered</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {services.map((service) => (
                <tr key={service.id}>
                  <td>
                    <strong>{service.name}</strong>
                    {service.description && (
                      <div className="faint small">{service.description}</div>
                    )}
                  </td>
                  <td>{formatDuration(service.duration_minutes)}</td>
                  <td className="price">₹{service.price.toFixed(2)}</td>
                  <td>
                    <span
                      className={`badge badge--${service.is_active ? 'open' : 'cancelled'}`}
                    >
                      {service.is_active ? 'Active' : 'Paused'}
                    </span>
                  </td>
                  <td>
                    <div className="btn-row">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => setEditing(service)}
                      >
                        Edit
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => toggleActive(service)}
                      >
                        {service.is_active ? 'Pause' : 'Resume'}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setDeleting(service)}
                      >
                        Delete
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ServiceFormModal
        open={formOpen || Boolean(editing)}
        service={editing}
        onClose={() => {
          setFormOpen(false)
          setEditing(null)
        }}
        onSaved={() => {
          setFormOpen(false)
          setEditing(null)
          load()
        }}
      />

      <ConfirmDialog
        open={Boolean(deleting)}
        title="Delete this service?"
        message={
          deleting
            ? `“${deleting.name}” will be removed. Open slots using it stay, just unlabelled. If a booked or completed slot uses it, deletion is refused — pause it instead.`
            : ''
        }
        confirmLabel="Delete service"
        pending={busy}
        onConfirm={remove}
        onClose={() => setDeleting(null)}
      />
    </>
  )
}

function ServiceFormModal({ open, service, onClose, onSaved }) {
  const toast = useToast()
  const editMode = Boolean(service)
  const [form, setForm] = useState({
    name: '',
    description: '',
    duration_minutes: 30,
    price: 0,
    is_active: true,
  })
  const [error, setError] = useState(null)
  const [pending, setPending] = useState(false)

  useEffect(() => {
    if (!open) return
    setError(null)
    setForm({
      name: service?.name || '',
      description: service?.description || '',
      duration_minutes: service?.duration_minutes ?? 30,
      price: service?.price ?? 0,
      is_active: service?.is_active ?? true,
    })
  }, [open, service])

  const update = (key) => (event) =>
    setForm((current) => ({ ...current, [key]: event.target.value }))

  async function submit(event) {
    event.preventDefault()
    setError(null)
    setPending(true)
    const payload = {
      name: form.name.trim(),
      description: form.description.trim() || null,
      duration_minutes: Number(form.duration_minutes),
      price: Number(form.price),
      is_active: Boolean(form.is_active),
    }
    try {
      if (editMode) {
        await api.updateService(service.id, payload)
        toast.success('Service updated.')
      } else {
        await api.createService(payload)
        toast.success('Service created.')
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
      title={editMode ? 'Edit service' : 'New service'}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button form="service-form" type="submit" pending={pending}>
            {editMode ? 'Save changes' : 'Create service'}
          </Button>
        </>
      }
    >
      <form id="service-form" onSubmit={submit} noValidate>
        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}
        <Field
          label="Name"
          required
          maxLength={120}
          value={form.name}
          onChange={update('name')}
        />
        <Field
          as="textarea"
          rows={2}
          label="Description (optional)"
          maxLength={500}
          value={form.description}
          onChange={update('description')}
        />
        <div className="form-grid">
          <Field
            label="Duration (minutes)"
            type="number"
            min={5}
            max={480}
            required
            value={form.duration_minutes}
            onChange={update('duration_minutes')}
          />
          <Field
            label="Price (₹)"
            type="number"
            min={0}
            step="0.01"
            required
            value={form.price}
            onChange={update('price')}
          />
        </div>
        <Field
          as="select"
          label="Offered to patients"
          value={form.is_active ? 'yes' : 'no'}
          onChange={(event) =>
            setForm((current) => ({
              ...current,
              is_active: event.target.value === 'yes',
            }))
          }
        >
          <option value="yes">Yes — show in booking</option>
          <option value="no">No — paused</option>
        </Field>
      </form>
    </Modal>
  )
}
