/**
 * `pending` shows progress and blocks the click. Mutating buttons must always pass it:
 * a double-clicked "Book" is exactly the race the backend is defending against, and
 * there is no reason to send the second request.
 */
export default function Button({
  children,
  variant = 'primary',
  size = 'md',
  pending = false,
  disabled = false,
  title,
  type = 'button',
  ...rest
}) {
  const isDisabled = disabled || pending
  return (
    <button
      type={type}
      className={`btn btn--${variant} btn--${size}`}
      disabled={isDisabled}
      aria-busy={pending || undefined}
      // A disabled <button> swallows hover events, so the tooltip lives on a wrapper
      // when needed; a plain title still works for the enabled case.
      title={title}
      {...rest}
    >
      {pending && <span className="btn__spinner" aria-hidden="true" />}
      {children}
    </button>
  )
}
