const LABELS = {
  OPEN: 'Open',
  BOOKED: 'Booked',
  COMPLETED: 'Completed',
  CANCELLED: 'Cancelled',
}

export default function StatusBadge({ status }) {
  if (!status) return null
  return (
    <span className={`badge badge--${status.toLowerCase()}`}>
      {LABELS[status] ?? status}
    </span>
  )
}
