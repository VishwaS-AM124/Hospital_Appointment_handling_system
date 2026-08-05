import { useEffect, useState } from 'react'

import Button from './Button'
import Field from './Field'
import Modal from './Modal'

/**
 * Confirmation for a destructive or irreversible action, with an optional free-text
 * note (cancellation reason, doctor's notes).
 */
export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  variant = 'danger',
  noteLabel,
  notePlaceholder,
  pending = false,
  onConfirm,
  onClose,
}) {
  const [note, setNote] = useState('')

  useEffect(() => {
    if (open) setNote('')
  }, [open])

  return (
    <Modal
      open={open}
      title={title}
      onClose={pending ? () => {} : onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            Keep it
          </Button>
          <Button
            variant={variant}
            pending={pending}
            onClick={() => onConfirm(note.trim() || null)}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      {message && <p className="dialog-message">{message}</p>}
      {noteLabel && (
        <Field
          as="textarea"
          rows={3}
          label={noteLabel}
          placeholder={notePlaceholder}
          value={note}
          maxLength={500}
          onChange={(event) => setNote(event.target.value)}
        />
      )}
    </Modal>
  )
}
