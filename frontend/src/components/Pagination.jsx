import Button from './Button'

export default function Pagination({ page, pages, total, onChange }) {
  if (!total) return null
  return (
    <nav className="pagination" aria-label="Pagination">
      <Button
        variant="ghost"
        size="sm"
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
      >
        ← Previous
      </Button>
      <span className="pagination__label">
        Page {page} of {Math.max(pages, 1)} · {total} total
      </span>
      <Button
        variant="ghost"
        size="sm"
        disabled={page >= pages}
        onClick={() => onChange(page + 1)}
      >
        Next →
      </Button>
    </nav>
  )
}
