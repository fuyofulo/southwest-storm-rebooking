import { short, STATUS_HELP } from './format.js'

export function Status({ status }) {
  return (
    <span className={`status ${status}`} title={STATUS_HELP[status]}>
      <i aria-hidden="true" />
      {status}
    </span>
  )
}

function Suggestion({ s }) {
  if (!s.suggestion) return <span className="faint">No flight met the rules</span>
  const flights = s.suggestion.flights
  if (flights.length === 1) {
    const f = flights[0]
    return (
      <span className="mono">
        {f.flight_no} <span className="faint">{short(f.departure_datetime)}</span>
      </span>
    )
  }
  return (
    <span className="mono" title={flights.map((f) => `${f.flight_no} ${short(f.departure_datetime)} ×${f.passengers}`).join('\n')}>
      {flights.map((f, i) => (
        <span key={f.flight_no} className="seg">
          {i > 0 && <span className="faint sep">+</span>}
          {f.flight_no}
          <span className="faint">×{f.passengers}</span>
        </span>
      ))}
    </span>
  )
}

export function BookingList({ items, selectedId, busyId, onOpen, onConfirm }) {
  return (
    <div className="list" role="region" aria-label="Bookings waiting">
      <table>
        <thead>
          <tr>
            <th title="lead_passenger_name · booking_id">Lead passenger</th>
            <th className="num" title="party_size">Party</th>
            <th title="origin_airport → destination_airport">Route</th>
            <th title="earliest_acceptable_departure">Earliest</th>
            <th>Suggestion</th>
            <th title="suggestion_status">Status</th>
            <th aria-label="Confirm" />
          </tr>
        </thead>
        <tbody>
          {items.map((s) => {
            const selected = s.booking_id === selectedId
            const busy = busyId === s.booking_id
            return (
              <tr
                key={s.booking_id}
                id={`row-${s.booking_id}`}
                className={selected ? 'is-selected' : undefined}
                aria-selected={selected}
                onClick={() => onOpen(s.booking_id)}
              >
                <td className="who">
                  <div className="name">{s.lead_passenger_name}</div>
                  <div className="mono faint id">{s.booking_id}</div>
                </td>
                <td className="num">{s.party_size}</td>
                <td className="mono">
                  {s.origin_airport}
                  <span className="faint"> → </span>
                  {s.destination_airport}
                </td>
                <td>{short(s.earliest_acceptable_departure)}</td>
                <td className="sugg">
                  <Suggestion s={s} />
                </td>
                <td>
                  <Status status={s.suggestion_status} />
                </td>
                <td className="act">
                  <button
                    className="quiet"
                    disabled={busy}
                    onClick={(e) => {
                      e.stopPropagation()
                      onConfirm(s)
                    }}
                  >
                    {busy ? 'Saving' : 'Confirm'}
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
