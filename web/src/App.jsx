import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { confirmBooking, fetchWaiting } from './api.js'
import { STATUS_LABEL, suggestionLines, when } from './format.js'

const AGENT_KEY = 'rebooking.agent'

function readAgent() {
  try {
    return localStorage.getItem(AGENT_KEY) || ''
  } catch {
    return ''
  }
}

function saveAgent(name) {
  try {
    localStorage.setItem(AGENT_KEY, name)
  } catch {
    // private window or blocked storage: the name just isn't remembered
  }
}

export default function App() {
  const [items, setItems] = useState([])
  const [phase, setPhase] = useState('loading') // loading | ready | error
  const [loadError, setLoadError] = useState(null)
  const [elapsed, setElapsed] = useState(0)
  const [selectedId, setSelectedId] = useState(null)
  const [agent, setAgent] = useState(readAgent)
  const [agreed, setAgreed] = useState({}) // booking_id -> family agreed (and agent checks done)
  const [busyId, setBusyId] = useState(null)
  const [confirmError, setConfirmError] = useState(null) // { id, message }
  const [needsAgreement, setNeedsAgreement] = useState(null) // booking_id whose Confirm was clicked too early
  const [toast, setToast] = useState(null)
  const agentInput = useRef(null)

  const load = useCallback(async () => {
    setPhase('loading')
    setLoadError(null)
    setElapsed(0)
    const started = Date.now()
    const tick = setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 1000)
    try {
      const data = await fetchWaiting()
      setItems(data)
      setSelectedId((cur) => (data.some((s) => s.booking_id === cur) ? cur : data[0]?.booking_id ?? null))
      setPhase('ready')
    } catch (err) {
      setLoadError(err.message)
      setPhase('error')
    } finally {
      clearInterval(tick)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const selected = useMemo(() => items.find((s) => s.booking_id === selectedId) || null, [items, selectedId])

  // Arrow keys move through the list (fast scanning without the mouse).
  useEffect(() => {
    function onKey(e) {
      if (!['ArrowDown', 'ArrowUp'].includes(e.key) || ['INPUT', 'TEXTAREA', 'BUTTON'].includes(e.target.tagName)) return
      e.preventDefault()
      setSelectedId((cur) => {
        const i = items.findIndex((s) => s.booking_id === cur)
        const next = items[Math.min(Math.max(i + (e.key === 'ArrowDown' ? 1 : -1), 0), items.length - 1)]
        document.getElementById(`row-${next?.booking_id}`)?.scrollIntoView({ block: 'nearest' })
        return next?.booking_id ?? cur
      })
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [items])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 6000)
    return () => clearTimeout(t)
  }, [toast])

  function open(id) {
    setSelectedId(id)
    setConfirmError(null)
  }

  function removeAndAdvance(id) {
    // Open the next booking straight away, so the agent can move on without another click.
    const i = items.findIndex((s) => s.booking_id === id)
    const rest = items.filter((s) => s.booking_id !== id)
    setItems(rest)
    setSelectedId(rest[Math.min(i, rest.length - 1)]?.booking_id ?? null)
  }

  async function confirm(s) {
    setConfirmError(null)
    if (!agent.trim()) {
      setConfirmError({ id: s.booking_id, message: 'Enter your name at the top before confirming.' })
      setSelectedId(s.booking_id)
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
      const record = await confirmBooking(s.booking_id, agent.trim(), s.suggestion?.option_id ?? null)
      setToast(`${s.booking_id} confirmed by ${record.confirmed_by}. Recorded only: book it in Southwest's system.`)
      removeAndAdvance(s.booking_id)
    } catch (err) {
      if (err.status === 409 && /already confirmed/i.test(err.message)) {
        setToast(`${s.booking_id} was already confirmed by another agent. Removed from your list.`)
        removeAndAdvance(s.booking_id)
      } else {
        setConfirmError({ id: s.booking_id, message: err.message })
      }
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="app">
      <header className="top">
        <div>
          <h1>Denver storm rebooking</h1>
          <p className="sub">
            {phase === 'ready' ? `${items.length} booking${items.length === 1 ? '' : 's'} waiting, newest cancellation first` : 'Rebooking queue'}
            {' · '}The assistant only suggests. Confirm records your decision; it never books a flight.
          </p>
        </div>
        <div className="top-actions">
          <label className="agent">
            <span>Agent</span>
            <input
              ref={agentInput}
              value={agent}
              placeholder="Your name"
              onChange={(e) => {
                setAgent(e.target.value)
                saveAgent(e.target.value)
              }}
            />
          </label>
          <button className="ghost" onClick={load} disabled={phase === 'loading'}>
            Refresh
          </button>
        </div>
      </header>

      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}

      {phase === 'loading' && (
        <div className="state">
          <p className="state-title">Loading the waiting bookings from the rebooking service… {elapsed}s</p>
          <p>The first load can take a minute or two while the AI model is asked about bookings it hasn't seen yet. After that it's instant.</p>
        </div>
      )}

      {phase === 'error' && (
        <div className="state error" role="alert">
          <p className="state-title">The rebooking service isn't responding.</p>
          <p>{loadError}</p>
          <p>
            Start it with <code>./run.sh serve</code> (or <code>./run.sh app</code> for the service and this page together), then try again.
          </p>
          <button onClick={load}>Try again</button>
        </div>
      )}

      {phase === 'ready' && items.length === 0 && (
        <div className="state">
          <p className="state-title">No bookings waiting.</p>
          <p>Every cancelled booking has been confirmed by an agent.</p>
        </div>
      )}

      {phase === 'ready' && items.length > 0 && (
        <main className="layout">
          <BookingList items={items} selectedId={selectedId} busyId={busyId} onOpen={open} onConfirm={confirm} />
          {selected && (
            <Detail
              key={selected.booking_id}
              s={selected}
              agreed={!!agreed[selected.booking_id]}
              onAgree={(v) => {
                setAgreed((cur) => ({ ...cur, [selected.booking_id]: v }))
                if (v) setNeedsAgreement(null)
              }}
              needsAgreement={needsAgreement === selected.booking_id}
              busy={busyId === selected.booking_id}
              error={confirmError?.id === selected.booking_id ? confirmError.message : null}
              onConfirm={() => confirm(selected)}
            />
          )}
        </main>
      )}
    </div>
  )
}

function StatusBadge({ status }) {
  return (
    <span className={`badge ${status}`} title={STATUS_LABEL[status]}>
      {status}
    </span>
  )
}

function BookingList({ items, selectedId, busyId, onOpen, onConfirm }) {
  return (
    <section className="list" aria-label="Waiting bookings">
      <table>
        <thead>
          <tr>
            <th>Booking</th>
            <th>Lead passenger</th>
            <th className="num">Party</th>
            <th>Route</th>
            <th>Earliest departure</th>
            <th>Suggestion</th>
            <th>Status</th>
            <th aria-label="Confirm" />
          </tr>
        </thead>
        <tbody>
          {items.map((s) => (
            <tr
              key={s.booking_id}
              id={`row-${s.booking_id}`}
              className={s.booking_id === selectedId ? 'selected' : ''}
              onClick={() => onOpen(s.booking_id)}
            >
              <td className="mono nowrap">{s.booking_id}</td>
              <td className="nowrap">{s.lead_passenger_name}</td>
              <td className="num">{s.party_size}</td>
              <td className="mono nowrap">
                {s.origin_airport}→{s.destination_airport}
              </td>
              <td className="nowrap">{when(s.earliest_acceptable_departure)}</td>
              <td className={s.suggestion ? 'mono nowrap' : 'muted'}>
                {suggestionLines(s).map((line) => (
                  <div key={line}>{line}</div>
                ))}
              </td>
              <td>
                <StatusBadge status={s.suggestion_status} />
              </td>
              <td>
                <button
                  className="small"
                  disabled={busyId === s.booking_id}
                  onClick={(e) => {
                    e.stopPropagation()
                    onConfirm(s)
                  }}
                >
                  {busyId === s.booking_id ? 'Saving…' : 'Confirm'}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

function Detail({ s, agreed, onAgree, needsAgreement, busy, error, onConfirm }) {
  const isSplit = s.suggestion_status === 'split_party_confirm'
  const flights = s.suggestion?.flights || []
  const failed = s.checklist.filter((c) => !c.passed)
  const ai = s.ai

  return (
    <aside className="detail" aria-label={`Booking ${s.booking_id}`}>
      <div className="detail-head">
        <div>
          <h2 className="mono">{s.booking_id}</h2>
          <p>
            {s.lead_passenger_name} · party of {s.party_size} · {s.origin_airport}→{s.destination_airport}
          </p>
        </div>
        <StatusBadge status={s.suggestion_status} />
      </div>

      {s.suggestion_status === 'no_option_found' && (
        <div className="banner none">
          <strong>No flight met the rules.</strong> {s.message?.replace(/^No flight met the rules[:.]?\s*/, '')}
          <p>Handle this booking by hand or escalate it, then Confirm to record your decision and clear it from the list.</p>
        </div>
      )}
      {isSplit && (
        <div className={`banner split${needsAgreement ? ' attention' : ''}`}>
          <strong>Split party: the family must agree before you confirm.</strong> No flight has {s.party_size} seats side by side, so the
          party flies on {flights.length} different flights. If they say no, escalate.
        </div>
      )}

      <dl className="facts">
        <Fact label="Earliest acceptable departure" field="earliest_acceptable_departure" value={when(s.earliest_acceptable_departure)} />
        <Fact label="Waiver eligible" field="waiver_eligible" value={s.waiver_eligible ? 'Yes: storm waiver applies' : 'No: original fare rules'} />
        {s.fare && <Fact label="Fare result" field="fare" value={s.fare.result} title={s.fare.detail} />}
        <Fact label="Original fare" field="fare_class" value={`${s.agent_context.fare_class}, $${s.agent_context.fare_paid_usd}`} />
      </dl>

      {flights.map((f, i) => (
        <FlightCard key={f.flight_no} f={f} index={i} isSplit={isSplit} />
      ))}

      {ai && (
        <div className="reason">
          <div className="label">{ai.used_fallback ? 'Reason (code choice, the model did not answer)' : `Model's reason · ${ai.model}`}</div>
          <p>{ai.reason || '—'}</p>
          {ai.used_fallback && <p className="muted small-text">Why no model reason: {ai.fallback_reason}</p>}
        </div>
      )}

      <Context s={s} />

      {s.documentation_lines.length > 0 && (
        <div className="block">
          <div className="label">Record on each flight</div>
          {s.documentation_lines.map((d) => (
            <div key={d} className="mono">
              {d}
            </div>
          ))}
        </div>
      )}

      <details className="block checklist">
        <summary>
          {failed.length
            ? `${failed.length} rule check(s) failed`
            : s.suggestion
              ? `All ${s.checklist.length} rule checks passed`
              : `${s.checklist.length} routing checks passed; no flight passed the flight rules`}
        </summary>
        <ul>
          {s.checklist.map((c) => (
            <li key={c.rule} className={c.passed ? 'pass' : 'fail'}>
              <span>{c.passed ? '✓' : '✗'}</span> {c.rule}: <span className="muted">{c.detail}</span>
            </li>
          ))}
        </ul>
      </details>

      <div className="confirm-bar">
        {isSplit && (
          <label className={`agree${needsAgreement ? ' attention' : ''}`}>
            <input type="checkbox" checked={agreed} onChange={(e) => onAgree(e.target.checked)} />
            <span>
              The family agreed to this split
              {s.agent_checks.map((c) => (
                <span key={c} className="check-line">
                  , and {c.replace(/^Make-up not stated: confirm /, '').replace(/ \(no child.*$/, '')}
                </span>
              ))}
              .
            </span>
          </label>
        )}
        {needsAgreement && <p className="error-text">Tick the box once the family has agreed, then Confirm.</p>}
        {error && (
          <p className="error-text" role="alert">
            {error}
          </p>
        )}
        <button className="primary" disabled={busy || (isSplit && !agreed)} onClick={onConfirm}>
          {busy ? 'Saving…' : s.suggestion ? `Confirm ${s.suggestion.flights.map((f) => f.flight_no).join(' + ')}` : 'Confirm: handled outside the helper'}
        </button>
      </div>
    </aside>
  )
}

function Fact({ label, field, value, title }) {
  return (
    <div className="fact" title={title}>
      <dt>
        {label} <code>{field}</code>
      </dt>
      <dd>{value}</dd>
    </div>
  )
}

function FlightCard({ f, index, isSplit }) {
  const heading = !isSplit ? 'Suggested flight' : f.includes_lead_passenger ? "Lead passenger's group" : `Group ${index + 1}, on a different flight`
  return (
    <div className="flight">
      <div className="flight-head">
        <span className="label">{heading}</span>
        <span className="flight-no mono">{f.flight_no}</span>
      </div>
      <dl className="facts four">
        <Fact label="Departs" field="departure_datetime" value={when(f.departure_datetime)} />
        <Fact label="Open seats" field="open_seats_total" value={f.open_seats_total} />
        <Fact label="Side by side" field="open_seats_adjacent_max" value={f.open_seats_adjacent_max} />
        <Fact label="Status" field="flight_status" value={f.flight_status + (f.weather_risk_flag ? ' · weather risk' : '')} />
      </dl>
      <p className="seated">
        <strong>
          {f.passengers} seated together{isSplit ? ` on ${f.flight_no}` : ''}:
        </strong>{' '}
        {f.seated_together.map((p, i) => (
          <span key={p}>
            {i > 0 && ', '}
            {i === 0 && f.includes_lead_passenger ? <strong>{p} (lead)</strong> : p}
          </span>
        ))}
      </p>
    </div>
  )
}

function Context({ s }) {
  const c = s.agent_context
  const bits = [
    c.agent_note && `Note: “${c.agent_note}”`,
    c.onward_connection_flight_no && `Onward connection ${c.onward_connection_flight_no}`,
    c.has_checked_bags && 'Checked bags',
    c.needs_wheelchair_assist && 'Wheelchair assist',
    c.travels_with_infant && 'Travels with infant',
    c.loyalty_tier && c.loyalty_tier !== 'None' && `${c.loyalty_tier} member`,
  ].filter(Boolean)
  if (!bits.length) return null
  return (
    <div className="block context">
      <div className="label">From the booking</div>
      <p>{bits.join(' · ')}</p>
    </div>
  )
}
