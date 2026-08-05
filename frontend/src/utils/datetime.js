/**
 * Timezone boundary for the client.
 *
 * The API stores and returns UTC with an explicit `Z`, and refuses input without an
 * offset. So: everything leaving here is `toISOString()` (always UTC), and everything
 * arriving is rendered in the browser's local timezone.
 */

/** Minutes east of UTC for the browser, e.g. +330 for IST. */
export function tzOffsetMinutes() {
  // getTimezoneOffset() returns minutes to ADD to local to reach UTC (-330 for IST),
  // so negate it to get the conventional "east is positive" offset the API expects.
  return -new Date().getTimezoneOffset()
}

/** `<input type="datetime-local">` value (local wall clock) -> UTC ISO-8601. */
export function toIsoUtc(localValue) {
  if (!localValue) return null
  const parsed = new Date(localValue)
  if (Number.isNaN(parsed.getTime())) return null
  return parsed.toISOString()
}

/** UTC ISO-8601 -> `<input type="datetime-local">` value in local time. */
export function toLocalInputValue(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (n) => String(n).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  )
}

/** `YYYY-MM-DD` for a date input, in local time. */
export function toLocalDateValue(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** Local start-of-day for a `YYYY-MM-DD` value, as UTC ISO — for date-range filters. */
export function dateStartIso(dateValue) {
  if (!dateValue) return null
  return new Date(`${dateValue}T00:00`).toISOString()
}

/** Local start of the *next* day, so a range filter includes the whole end date. */
export function dateEndIso(dateValue) {
  if (!dateValue) return null
  const date = new Date(`${dateValue}T00:00`)
  date.setDate(date.getDate() + 1)
  return date.toISOString()
}

export function formatTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

export function formatDateTime(iso) {
  if (!iso) return ''
  return `${formatDate(iso)} · ${formatTime(iso)}`
}

/** "Mon 10 Aug 2026 · 09:00 – 09:30" */
export function formatRange(startIso, endIso) {
  if (!startIso) return ''
  return `${formatDate(startIso)} · ${formatTime(startIso)} – ${formatTime(endIso)}`
}

export function formatDuration(minutes) {
  if (!minutes && minutes !== 0) return ''
  if (minutes < 60) return `${minutes} min`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest ? `${hours} h ${rest} min` : `${hours} h`
}

/** Groups items into `[{ dateIso, label, items }]` buckets by local calendar day. */
export function groupByLocalDate(items, getIso) {
  const buckets = new Map()
  for (const item of items) {
    const iso = getIso(item)
    const key = toLocalDateValue(iso)
    if (!buckets.has(key)) buckets.set(key, { key, label: formatDate(iso), items: [] })
    buckets.get(key).items.push(item)
  }
  return [...buckets.values()]
}

export function isPast(iso) {
  if (!iso) return false
  return new Date(iso).getTime() <= Date.now()
}

/** "in 3 days" / "2 hours ago" — used for at-a-glance context on lists. */
export function relativeTime(iso) {
  if (!iso) return ''
  const deltaMs = new Date(iso).getTime() - Date.now()
  const units = [
    ['day', 86_400_000],
    ['hour', 3_600_000],
    ['minute', 60_000],
  ]
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
  for (const [unit, ms] of units) {
    if (Math.abs(deltaMs) >= ms || unit === 'minute') {
      return formatter.format(Math.round(deltaMs / ms), unit)
    }
  }
  return ''
}

/** Today's date as `YYYY-MM-DD`, for date-input min attributes. */
export function todayDateValue() {
  return toLocalDateValue(new Date().toISOString())
}
