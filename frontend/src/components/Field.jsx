import { useId } from 'react'

/** Labelled input. Always renders a real <label for>, so the control is accessible. */
export default function Field({
  label,
  hint,
  error,
  as = 'input',
  children,
  ...rest
}) {
  const id = useId()
  const describedBy = [hint && `${id}-hint`, error && `${id}-error`]
    .filter(Boolean)
    .join(' ')

  const Control = as
  return (
    <div className={`field${error ? ' field--error' : ''}`}>
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      <Control
        id={id}
        className="field__control"
        aria-describedby={describedBy || undefined}
        aria-invalid={error ? true : undefined}
        {...rest}
      >
        {children}
      </Control>
      {hint && (
        <p className="field__hint" id={`${id}-hint`}>
          {hint}
        </p>
      )}
      {error && (
        <p className="field__error" id={`${id}-error`}>
          {error}
        </p>
      )}
    </div>
  )
}
