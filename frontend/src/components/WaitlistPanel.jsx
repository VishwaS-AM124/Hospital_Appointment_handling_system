import { useCallback, useEffect, useState } from 'react'

import * as api from '../api/endpoints'
import { formatRange } from '../utils/datetime'
import Button from './Button'
import EmptyState from './EmptyState'
import Spinner from './Spinner'
import { useToast } from './Toast'

/** Minutes left in an exclusive claim window, or null if there isn't one. */
function minutesLeft(iso) {
  if (!iso) return null
  const ms = new Date(iso).getTime() - Date.now()
  return ms <= 0 ? 0 : Math.ceil(ms / 60_000)
}

/**
 * The patient's side of the waiting queue.
 *
 * Shows their place in line for each taken slot, and — when they reach the front and the
 * slot is released — a live "Book it now" button for the duration of their exclusive
 * claim window.
 */
export default function WaitlistPanel({ onBooked }) {
  const toast = useToast()
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState(null)
  // Re-render once a minute so the countdown stays honest.
  const [, setTick] = useState(0)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setEntries(await api.listMyWaitlist(true))
    } catch (caught) {
      toast.error(caught.message)
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    const timer = window.setInterval(() => setTick((n) => n + 1), 30_000)
    return () => window.clearInterval(timer)
  }, [])

  async function claim(entry) {
    setBusyId(entry.id)
    try {
      await api.bookAppointment(entry.slot_id, 'Claimed from the waiting list')
      toast.success('Booked. The slot is yours.')
      await load()
      onBooked?.()
    } catch (caught) {
      toast.error(caught.message)
      await load()
    } finally {
      setBusyId(null)
    }
  }

  async function leave(entry) {
    setBusyId(entry.id)
    try {
      await api.leaveWaitlist(entry.slot_id)
      toast.info('You have left that waiting list.')
      await load()
    } catch (caught) {
      toast.error(caught.message)
    } finally {
      setBusyId(null)
    }
  }

  if (loading) return <Spinner label="Loading your waiting lists…" />

  if (entries.length === 0) {
    return (
      <EmptyState title="You are not waiting for any slots" icon="⏳">
        If you try to book a slot that someone takes first, we will put you in its queue
        automatically and notify you if it frees up.
      </EmptyState>
    )
  }

  return (
    <div className="slot-list">
      {entries.map((entry) => {
        const offered = entry.status === 'OFFERED'
        const claimable = entry.can_claim_now
        const left = minutesLeft(entry.offer_expires_at)
        return (
          <article
            className={`slot ${claimable ? 'slot--open' : 'slot--booked'}`}
            key={entry.id}
          >
            <div className="slot__time">
              {formatRange(entry.slot?.start_at, entry.slot?.end_at)}
              <small>
                {entry.slot?.doctor?.full_name || 'Doctor'}
                {entry.slot?.service ? ` · ${entry.slot.service.name}` : ''}
              </small>
            </div>

            <div className="slot__main">
              {claimable ? (
                <>
                  <p className="slot__title">This slot is being held for you</p>
                  <div className="slot__meta">
                    <span className="badge badge--open">Your turn</span>
                    <span>
                      {left > 0
                        ? `About ${left} minute${left === 1 ? '' : 's'} left to claim it`
                        : 'Expiring now'}
                    </span>
                  </div>
                </>
              ) : (
                <>
                  <p className="slot__title">
                    You are #{entry.position ?? '—'} in the queue
                  </p>
                  <div className="slot__meta">
                    <span className="badge badge--booked">Waiting</span>
                    <span>
                      {offered
                        ? 'Your claim window has just lapsed.'
                        : 'We will notify you if this slot frees up.'}
                    </span>
                  </div>
                </>
              )}
            </div>

            <div className="slot__side">
              {claimable && (
                <Button
                  size="sm"
                  pending={busyId === entry.id}
                  onClick={() => claim(entry)}
                >
                  Book it now
                </Button>
              )}
              <Button
                variant="ghost"
                size="sm"
                pending={busyId === entry.id && !claimable}
                onClick={() => leave(entry)}
              >
                Leave queue
              </Button>
            </div>
          </article>
        )
      })}
    </div>
  )
}
