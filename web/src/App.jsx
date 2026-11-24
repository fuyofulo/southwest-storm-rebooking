import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { confirmBooking, fetchConfirmed, fetchWaiting } from './api.js'
import { day, duration, initials, matches } from './format.js'
import { BookingList } from './List.jsx'
import { Detail } from './Detail.jsx'
import { Check, ChevronLeft, ChevronRight, Moon, Refresh, Search, Sun } from './icons.jsx'

const AGENT_KEY = 'rebooking.agent'
const THEME_KEY = 'rebooking.theme'

// The first four look at bookings still waiting; Confirmed is the ones already done.
const FILTERS = [
  { id: 'all', label: 'Waiting' },
  { id: 'ready_to_confirm', label: 'Ready' },
  { id: 'split_party_confirm', label: 'Split' },
  { id: 'no_option_found', label: 'No option' },
  { id: 'confirmed', label: 'Confirmed', apart: true },
]

const CONFIRMATION_FIELDS = ['booking_id', 'confirmed_by', 'confirmed_at', 'suggestion_status', 'option_id', 'flight_nos', 'seconds_to_confirm']
const GOAL_SECONDS = 7 * 60 // the target: under 7 minutes per itinerary, down from about 14

// Storage can be blocked (private window, previews): the page works without it.
function readStored(key) {
  try {
    return localStorage.getItem(key) || ''
  } catch {
    return ''
  }
}
function store(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* not remembered, that's all */
  }
}

function systemDark() {
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  } catch {
    return false
  }
}

function isTyping(el) {
  if (!el) return false
  if (el.isContentEditable || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT') return true
  return el.tagName === 'INPUT' && !['checkbox', 'radio', 'button', 'submit'].includes(el.type)
}

function CenterState({ tone, title, children }) {
  return (
    <div className={`state${tone ? ` ${tone}` : ''}`} role={tone === 'error' ? 'alert' : 'status'}>
      <p className="state-title">{title}</p>
      {children}
    </div>
  )
}

export default function App() {
  const [items, setItems] = useState([]) // waiting
  const [done, setDone] = useState([]) // already confirmed, most recent first
  const [phase, setPhase] = useState('loading') // loading | ready | error
  const [refreshing, setRefreshing] = useState(false)
  const [loadError, setLoadError] = useState(null)
  const [elapsed, setElapsed] = useState(0)
  const [selectedId, setSelectedId] = useState(null)
  const [agent, setAgent] = useState(() => readStored(AGENT_KEY))
  const [agreed, setAgreed] = useState({}) // booking_id -> the family agreed to the split
  const [busyId, setBusyId] = useState(null)
  const [confirmError, setConfirmError] = useState(null) // { id, message }
  const [needsAgreement, setNeedsAgreement] = useState(null) // booking_id whose Confirm came before the tick
  const [toast, setToast] = useState(null)
  const [filter, setFilter] = useState('all')
  const [query, setQuery] = useState('')
  const [theme, setTheme] = useState(() => readStored(THEME_KEY) || null)
  const agentInput = useRef(null)
  const searchInput = useRef(null)
  const openedAt = useRef(new Map()) // booking_id -> when the agent first opened it (for the time to confirm)

  const load = useCallback(async ({ quiet = false } = {}) => {
    // A refresh keeps the list on screen; only the first load shows the loading state.
    if (!quiet) {
      setPhase('loading')
      setElapsed(0)
    }
    setRefreshing(true)
    setLoadError(null)
    const started = Date.now()
    const tick = setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 1000)
    try {
      const [waiting, confirmed] = await Promise.all([fetchWaiting(), fetchConfirmed()])
      setItems(waiting)
      setDone(confirmed)
      setPhase('ready')
    } catch (err) {
      setLoadError(err.message)
      setPhase('error')
    } finally {
      clearInterval(tick)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    const root = document.documentElement
    if (theme) root.dataset.theme = theme
    else delete root.dataset.theme
  }, [theme])
  const dark = theme ? theme === 'dark' : systemDark()

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 5000)
    return () => clearTimeout(t)
  }, [toast])

  const counts = useMemo(() => {
    const c = { all: items.length, confirmed: done.length }
    for (const s of items) c[s.suggestion_status] = (c[s.suggestion_status] || 0) + 1
    return c
  }, [items, done])

  const visible = useMemo(
    () =>
      filter === 'confirmed'
        ? done.filter((s) => matches(s, query))
        : items.filter((s) => (filter === 'all' || s.suggestion_status === filter) && matches(s, query)),
    [items, done, filter, query],
  )
  const selected = visible.find((s) => s.booking_id === selectedId) || visible[0] || null
  const index = selected ? visible.indexOf(selected) : -1

  // The clock for a booking starts the first time it's open on screen and stops at Confirm.
  const openKey = phase === 'ready' && selected && !selected.confirmation ? selected.booking_id : null
  useEffect(() => {
    if (openKey && !openedAt.current.has(openKey)) openedAt.current.set(openKey, Date.now())
  }, [openKey])

  const timed = done.map((s) => s.confirmation?.seconds_to_confirm).filter((n) => Number.isFinite(n))
  const average = timed.length ? timed.reduce((a, b) => a + b, 0) / timed.length : null

  function open(id) {
    setSelectedId(id)
    setConfirmError(null)
  }

  function move(delta) {
    if (!visible.length) return
    const next = visible[Math.min(Math.max(index + delta, 0), visible.length - 1)]
    if (!next) return
    open(next.booking_id)
    requestAnimationFrame(() => document.getElementById(`row-${next.booking_id}`)?.scrollIntoView({ block: 'nearest' }))
  }

  function setAgree(id, value) {
    setAgreed((cur) => ({ ...cur, [id]: value }))
    if (value) setNeedsAgreement(null)
  }

  function removeAndAdvance(id) {
    // Open the next booking straight away so the agent can carry on without another click.
    // If the agent already moved to another booking while this one was saving, leave them there.
    const i = visible.findIndex((s) => s.booking_id === id)
    const rest = visible.filter((s) => s.booking_id !== id)
    const next = rest[Math.min(Math.max(i, 0), rest.length - 1)]?.booking_id ?? null
    setItems((cur) => cur.filter((s) => s.booking_id !== id))
    setSelectedId((cur) => (cur === null || cur === id || !rest.some((s) => s.booking_id === cur) ? next : cur))
  }

  async function confirm(s) {
    if (busyId || s.confirmation) return
    setConfirmError(null)
    if (!agent.trim()) {
      setSelectedId(s.booking_id)
      setConfirmError({ id: s.booking_id, message: 'Add your name at the top right, then confirm.' })
      agentInput.current?.focus()
      return
    }
    if (s.suggestion_status === 'split_party_confirm' && !agreed[s.booking_id]) {
      setSelectedId(s.booking_id)
      setNeedsAgreement(s.booking_id)
      return
    }
    setBusyId(s.booking_id)
    try {
      const started = openedAt.current.get(s.booking_id)
      const seconds = started ? Math.max(0, Math.round((Date.now() - started) / 1000)) : null
      const record = await confirmBooking(s.booking_id, agent.trim(), s.suggestion?.option_id ?? null, seconds)
      const confirmation = Object.fromEntries(CONFIRMATION_FIELDS.map((k) => [k, record[k]]))
      setDone((cur) => [{ ...s, confirmation }, ...cur.filter((x) => x.booking_id !== s.booking_id)])
      setToast(`${s.booking_id} recorded. Now book it in Southwest's system.`)
      removeAndAdvance(s.booking_id)
    } catch (err) {
      if (err.status === 409 && /already confirmed/i.test(err.message)) {
        setToast(`${s.booking_id} was already confirmed by another agent. It's under Confirmed.`)
        removeAndAdvance(s.booking_id)
        load({ quiet: true })
      } else {
        setConfirmError({ id: s.booking_id, message: err.message })
      }
    } finally {
      setBusyId(null)
    }
  }

  // Keyboard: j/k or arrows move, a ticks "family agreed", ⌘↵ confirms, / searches, r refreshes.
  const onKey = useRef(null)
  onKey.current = (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault()
      if (selected && phase === 'ready') confirm(selected)
      return
    }
    if (e.key === 'Escape' && e.target === searchInput.current) {
      setQuery('')
      e.target.blur()
      return
    }
    if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey || phase !== 'ready') return
    if (e.key === 'j' || e.key === 'ArrowDown') move(1)
    else if (e.key === 'k' || e.key === 'ArrowUp') move(-1)
    else if (e.key === '/') searchInput.current?.focus()
    else if (e.key === 'a' && selected?.suggestion_status === 'split_party_confirm' && !selected.confirmation)
      setAgree(selected.booking_id, !agreed[selected.booking_id])
    else if (e.key === 'r') load({ quiet: true })
    else return
    e.preventDefault()
  }
  useEffect(() => {
    const handler = (e) => onKey.current(e)
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  // What to say when the current view has nothing to show (never an empty panel).
  let empty = null
  if (phase === 'ready' && !visible.length) {
    const showWaiting = { label: `Show waiting (${items.length})`, run: () => (setFilter('all'), setQuery('')) }
    if (query) empty = { title: 'No bookings match', text: `Nothing here matches “${query}”.`, action: { label: 'Clear search', run: () => setQuery('') } }
    else if (filter === 'confirmed') empty = { title: 'Nothing confirmed yet', text: 'Bookings appear here once an agent confirms them.', action: items.length ? showWaiting : null }
    else if (!items.length)
      empty = {
        title: 'Nothing waiting',
        text: 'Every cancelled booking has been confirmed by an agent.',
        action: done.length ? { label: `See confirmed (${done.length})`, run: () => setFilter('confirmed') } : null,
      }
    else empty = { title: 'No bookings match', text: 'Nothing waiting has this status.', action: showWaiting }
  }

  const requestDate = (items[0] || done[0])?.request_date
  const live = phase === 'error' ? 'offline' : phase === 'loading' || refreshing ? 'loading' : 'live'

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="wordmark">rebook</span>
          <span className="tagline">Denver storm · November 2026</span>
        </div>
        <div className="top-actions">
          <label className={`agent${agent.trim() ? '' : ' empty'}`} title="Your name is saved with each confirmation">
            <span className="avatar" aria-hidden="true">
              {initials(agent)}
            </span>
            <input
              ref={agentInput}
              value={agent}
              placeholder="Your name"
              aria-label="Agent name"
              spellCheck={false}
              onChange={(e) => {
                setAgent(e.target.value)
                store(AGENT_KEY, e.target.value)
                if (confirmError) setConfirmError(null)
              }}
            />
          </label>
          <button
            className="icon"
            aria-label={dark ? 'Light theme' : 'Dark theme'}
            title={dark ? 'Light theme' : 'Dark theme'}
            onClick={() => {
              const next = dark ? 'light' : 'dark'
              setTheme(next)
              store(THEME_KEY, next)
            }}
          >
            {dark ? <Sun /> : <Moon />}
          </button>
          <button
            className={`icon${refreshing ? ' spinning' : ''}`}
            aria-label="Refresh"
            title="Refresh (r)"
            disabled={refreshing}
            onClick={() => load({ quiet: phase === 'ready' })}
          >
            <Refresh />
          </button>
        </div>
      </header>

      <div className="subbar">
        <div className="segmented" role="tablist" aria-label="Filter by suggestion_status">
          {FILTERS.map((f) => (
            <span key={f.id} className="seg-item">
              {f.apart && <span className="seg-divider" aria-hidden="true" />}
              <button role="tab" aria-selected={filter === f.id} className={filter === f.id ? 'on' : undefined} onClick={() => setFilter(f.id)}>
                {f.label}
                <span className="count">{counts[f.id] || 0}</span>
              </button>
            </span>
          ))}
        </div>

        <div className="pager">
          <button className="icon" aria-label="Previous booking" title="Previous (k)" disabled={index <= 0} onClick={() => move(-1)}>
            <ChevronLeft />
          </button>
          <span>
            Booking <strong>{index >= 0 ? index + 1 : '–'}</strong> of {visible.length}
          </span>
          <button
            className="icon"
            aria-label="Next booking"
            title="Next (j)"
            disabled={index < 0 || index >= visible.length - 1}
            onClick={() => move(1)}
          >
            <ChevronRight />
          </button>
        </div>

        <label className="search">
          <Search />
          <input
            ref={searchInput}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search name, booking, route or flight"
            aria-label="Search bookings"
            spellCheck={false}
          />
          <kbd>/</kbd>
        </label>
      </div>

      <main className="main">
        {phase === 'loading' && (
          <CenterState title={`Loading the waiting bookings · ${elapsed}s`}>
            <span className="pulse" aria-hidden="true" />
            <p>The first load can take a minute or two while the model is asked about bookings it hasn't seen. After that it's quick.</p>
          </CenterState>
        )}

        {phase === 'error' && (
          <CenterState tone="error" title="The rebooking service isn't responding">
            <p>{loadError}</p>
            <p>
              Start it with <code>./run.sh app</code> (or <code>./run.sh serve</code> for the service alone), then try again.
            </p>
            <button className="soft" onClick={() => load()}>
              Try again
            </button>
          </CenterState>
        )}

        {empty && (
          <CenterState title={empty.title}>
            <p>{empty.text}</p>
            {empty.action && (
              <button className="soft" onClick={empty.action.run}>
                {empty.action.label}
              </button>
            )}
          </CenterState>
        )}

        {phase === 'ready' && selected && (
          <>
            <BookingList items={visible} selectedId={selected.booking_id} busyId={busyId} onOpen={open} onConfirm={confirm} />
            <Detail
              key={selected.booking_id}
              s={selected}
              agreed={!!agreed[selected.booking_id]}
              onAgree={(v) => setAgree(selected.booking_id, v)}
              needsAgreement={needsAgreement === selected.booking_id}
              busy={busyId === selected.booking_id}
              error={confirmError?.id === selected.booking_id ? confirmError.message : null}
              onConfirm={() => confirm(selected)}
            />
          </>
        )}
      </main>

      <footer className="statusbar">
        <div className="status-left">
          <span className={`live ${live}`}>
            <i aria-hidden="true" />
            {live === 'offline' ? 'Offline' : live === 'loading' ? 'Loading' : 'Live'}
          </span>
          <span>
            <strong>{items.length}</strong> waiting
          </span>
          <span>
            <strong>{done.length}</strong> confirmed
          </span>
          {average !== null && (
            <span
              className={`avg${average <= GOAL_SECONDS ? ' on-goal' : ''}`}
              title={`Average time from opening a booking to clicking Confirm, over ${timed.length} confirmation${timed.length === 1 ? '' : 's'} timed by this page. Goal: under 7 minutes per itinerary.`}
            >
              avg <strong>{duration(average)}</strong> to confirm <span className="faint">· goal 7:00</span>
            </span>
          )}
          {requestDate && (
            <span className="wide-only">
              request date <strong>{day(requestDate)}</strong>
            </span>
          )}
        </div>
        <div className="keys">
          <span>
            <kbd>j</kbd>
            <kbd>k</kbd> move
          </span>
          <span>
            <kbd>a</kbd> family agreed
          </span>
          <span>
            <kbd>⌘</kbd>
            <kbd>↵</kbd> confirm
          </span>
          <span>
            <kbd>/</kbd> search
          </span>
        </div>
      </footer>

      {toast && (
        <div className="toast" role="status">
          <span className="toast-icon">
            <Check />
          </span>
          {toast}
        </div>
      )}
    </div>
  )
}
