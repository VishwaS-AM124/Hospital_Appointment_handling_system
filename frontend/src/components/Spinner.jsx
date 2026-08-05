export default function Spinner({ label = 'Loading…', full = false }) {
  return (
    <div className={full ? 'spinner-wrap spinner-wrap--full' : 'spinner-wrap'}>
      <span className="spinner" aria-hidden="true" />
      <span role="status">{label}</span>
    </div>
  )
}
