import { useCallback, useEffect, useRef, useState } from 'react'

import * as api from '../api/endpoints'
import { relativeTime } from '../utils/datetime'

const POLL_MS = 20_000

/** A small icon per notification type, so the list is scannable at a glance. */
const ICONS = {
  APPOINTMENT_BOOKED: '📗',
  APPOINTMENT_CANCELLED: '📕',
  APPOINTMENT_COMPLETED: '✅',
  SLOT_AVAILABLE: '🔔',
  WAITLIST_JOINED: '⏳',
  WAITLIST_MISSED: '⌛',
  SLOT_WITHDRAWN: '🚫',
}

export default function NotificationBell() {
  const [open, setOpen] = useState(false)
  const [unread, setUnread] = useState(0)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const panelRef = useRef(null)
  const buttonRef = useRef(null)

  const refreshCount = useCallback(async () => {
    try {
      const { unread: count } = await api.unreadCount()
      setUnread(count)
    } catch {
      // A failed poll is not worth interrupting the user for — the next tick retries.
    }
  }, [])

  // Poll for the badge. Real-time push (SSE/WebSocket) would be nicer; polling keeps
  // the deployment story simple and is more than adequate at this cadence.
  useEffect(() => {
    refreshCount()
    const timer = window.setInterval(refreshCount, POLL_MS)
    return () => window.clearInterval(timer)
  }, [refreshCount])

  const loadList = useCallback(async () => {
    setLoading(true)
    try {
      const page = await api.listNotifications({ page: 1, page_size: 20 })
      setItems(page.items)
    } catch {
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [])

  // Close on outside click or Escape.
  useEffect(() => {
    if (!open) return undefined

    function onPointerDown(event) {
      if (
        !panelRef.current?.contains(event.target) &&
        !buttonRef.current?.contains(event.target)
      ) {
        setOpen(false)
      }
    }
    function onKeyDown(event) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  function toggle() {
    const next = !open
    setOpen(next)
    if (next) loadList()
  }

  async function markRead(notification) {
    if (notification.read_at) return
    try {
      await api.markNotificationRead(notification.id)
      setItems((current) =>
        current.map((item) =>
          item.id === notification.id
            ? { ...item, read_at: new Date().toISOString() }
            : item,
        ),
      )
      setUnread((count) => Math.max(0, count - 1))
    } catch {
      /* leave it unread — the next poll corrects the badge */
    }
  }

  async function markAll() {
    try {
      await api.markAllNotificationsRead()
      const now = new Date().toISOString()
      setItems((current) =>
        current.map((item) => ({ ...item, read_at: item.read_at || now })),
      )
      setUnread(0)
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="bell-wrap">
      <button
        ref={buttonRef}
        type="button"
        className="bell"
        onClick={toggle}
        aria-expanded={open}
        aria-haspopup="true"
        aria-label={
          unread > 0 ? `Notifications, ${unread} unread` : 'Notifications'
        }
      >
        <span aria-hidden="true">🔔</span>
        {unread > 0 && (
          <span className="bell__badge">{unread > 9 ? '9+' : unread}</span>
        )}
      </button>

      {open && (
        <div className="bell-panel" ref={panelRef} role="dialog" aria-label="Notifications">
          <header className="bell-panel__header">
            <span>Notifications</span>
            {unread > 0 && (
              <button type="button" className="bell-panel__action" onClick={markAll}>
                Mark all read
              </button>
            )}
          </header>

          <div className="bell-panel__body">
            {loading ? (
              <p className="bell-panel__empty">Loading…</p>
            ) : items.length === 0 ? (
              <p className="bell-panel__empty">Nothing yet.</p>
            ) : (
              items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={
                    item.read_at ? 'note' : 'note note--unread'
                  }
                  onClick={() => markRead(item)}
                >
                  <span className="note__icon" aria-hidden="true">
                    {ICONS[item.type] || '•'}
                  </span>
                  <span className="note__text">
                    <span className="note__title">{item.title}</span>
                    {item.body && <span className="note__body">{item.body}</span>}
                    <span className="note__time">{relativeTime(item.created_at)}</span>
                  </span>
                  {!item.read_at && <span className="note__dot" aria-hidden="true" />}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
