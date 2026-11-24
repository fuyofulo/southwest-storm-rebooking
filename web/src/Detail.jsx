import { day, time, usd, when } from './format.js'
import { Status } from './List.jsx'
import { Check } from './icons.jsx'

const sentence = (t) => (t ? t.charAt(0).toUpperCase() + t.slice(1) : t)

function Fact({ label, field, value, title }) {
  return (
    <div className="fact" title={title ? `${field}: ${title}` : field}>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}

function Flight({ f, index, total, isSplit }) {
  const label = !isSplit ? 'Suggested flight' : f.includes_lead_passenger ? "Lead passenger's group" : 'Separate group, different flight'
  return (
    <article className="flight">
      <div className="flight-top">
        <div>
          <div className="flight-label">
            {isSplit && (
              <span className="step">
                {index + 1}/{total}
              </span>
            )}
            {label}
          </div>
          <div className="flight-no mono" title="flight_no">
            {f.flight_no}
          </div>
        </div>
        <div className="flight-when" title="departure_datetime">
          <div className="flight-time">{time(f.departure_datetime)}</div>
          <div className="flight-day">{day(f.departure_datetime)}</div>
        </div>
      </div>
      <dl className="flight-stats">
        <Fact label="Open seats" field="open_seats_total" value={f.open_seats_total} />
        <Fact label="Side by side" field="open_seats_adjacent_max" value={f.open_seats_adjacent_max} />
        <Fact label="Status" field="flight_status" value={sentence(f.flight_status) + (f.weather_risk_flag ? ' · weather risk' : '')} />
      </dl>
      <div className="seated">
        <div className="seated-label">{f.passengers === 1 ? '1 passenger' : `${f.passengers} seated together`}</div>
        <div className="pax-list">
          {f.seated_together.map((p, i) => {
            const lead = i === 0 && f.includes_lead_passenger
            return (
              <span key={p} className={`pax${lead ? ' lead' : ''}`}>
                {p}
                {lead && <em>lead</em>}
              </span>
            )
          })}
        </div>
      </div>
    </article>
  )
}

function Reason({ ai }) {
  const model = ai.model ? ai.model.split('/').pop().replace(/:free$/, '') : 'model'
  return (
    <section className={`reason${ai.used_fallback ? ' fallback' : ''}`}>
      <h3 className="section-label">
        {ai.used_fallback ? "Code's choice" : "Model's reason"}
        <span className="faint"> · {ai.used_fallback ? 'the model did not answer' : model}</span>
      </h3>
      <p>{ai.reason ? ai.reason.replace(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?/g, (ts) => when(ts)) : '—'}</p>
      {ai.used_fallback && ai.fallback_reason && <p className="faint small">{ai.fallback_reason}</p>}
    </section>
  )
}

function Context({ ctx }) {
  const chips = [
    ctx.onward_connection_flight_no && `Onward ${ctx.onward_connection_flight_no}`,
    ctx.has_checked_bags && 'Checked bags',
    ctx.needs_wheelchair_assist && 'Wheelchair assist',
    ctx.travels_with_infant && 'Travels with infant',
    ctx.loyalty_tier && ctx.loyalty_tier !== 'None' && ctx.loyalty_tier,
  ].filter(Boolean)
  if (!ctx.agent_note && !chips.length) return null
  return (
    <section className="block">
      <h3 className="section-label">From the booking</h3>
      {ctx.agent_note && <p className="quote">“{ctx.agent_note}”</p>}
      {chips.length > 0 && (
        <div className="chips">
          {chips.map((c) => (
            <span key={c}>{c}</span>
          ))}
        </div>
      )}
    </section>
  )
}

export function Detail({ s, agreed, onAgree, needsAgreement, busy, error, onConfirm }) {
  const isSplit = s.suggestion_status === 'split_party_confirm'
  const isNone = s.suggestion_status === 'no_option_found'
  const flights = s.suggestion?.flights || []
  const failed = s.checklist.filter((c) => !c.passed)
  const ctx = s.agent_context || {}
  const checks = (s.agent_checks || []).map((c) => c.replace(/^Make-up not stated: confirm /, '').replace(/ \(no child.*$/, ''))

  return (
    <aside className="detail" aria-label={`Booking ${s.booking_id}`}>
      <div className="detail-scroll">
        <header className="detail-head">
          <div>
            <div className="eyebrow mono" title="booking_id">
              {s.booking_id}
            </div>
            <h2 title="lead_passenger_name">{s.lead_passenger_name}</h2>
            <p className="sub">
              Party of {s.party_size}
              <span className="faint"> · </span>
              {s.origin_airport} → {s.destination_airport}
            </p>
          </div>
          <Status status={s.suggestion_status} />
        </header>

        {isSplit && (
          <div className={`note split${needsAgreement && !agreed ? ' attention' : ''}`}>
            <strong>The family must agree before you confirm.</strong>
            <p>
              No flight has {s.party_size} seats side by side, so the party flies on {flights.length} different flights, each group seated
              together. If they say no, escalate.
            </p>
          </div>
        )}
        {isNone && (
          <div className="note none">
            <strong>No flight met the rules.</strong>
            <p>{sentence(s.message?.replace(/^No flight met the rules[:.]?\s*/, ''))}</p>
            <p className="faint">Handle it by hand or escalate, then confirm to record that and clear it from the list.</p>
          </div>
        )}

        <dl className="facts">
          <Fact label="Earliest acceptable departure" field="earliest_acceptable_departure" value={when(s.earliest_acceptable_departure)} />
          <Fact label="Waiver eligible" field="waiver_eligible" value={s.waiver_eligible ? 'Yes · storm waiver' : 'No · original fare rules'} />
          <Fact label="Fare result" field="fare" value={s.fare ? sentence(s.fare.result) : 'No flight to price'} title={s.fare?.detail} />
          <Fact label="Original fare" field="fare_class · fare_paid_usd" value={`${ctx.fare_class} · ${usd(ctx.fare_paid_usd)}`} />
        </dl>

        {flights.length > 0 && (
          <section className="block">
            <h3 className="section-label">{isSplit ? `Suggestion · ${flights.length} flights` : 'Suggestion'}</h3>
            {flights.map((f, i) => (
              <Flight key={f.flight_no} f={f} index={i} total={flights.length} isSplit={isSplit} />
            ))}
          </section>
        )}

        {s.ai && <Reason ai={s.ai} />}

        <Context ctx={ctx} />

        {s.documentation_lines?.length > 0 && (
          <section className="block">
            <h3 className="section-label">Record on each flight</h3>
            {s.documentation_lines.map((d) => (
              <div key={d} className="mono record">
                {d}
              </div>
            ))}
          </section>
        )}

        <details className="checks">
          <summary>
            <span className={failed.length ? 'bad' : 'good'}>{failed.length ? '✕' : <Check />}</span>
            {failed.length
              ? `${failed.length} rule check(s) failed`
              : s.suggestion
                ? `All ${s.checklist.length} rule checks passed`
                : `${s.checklist.length} routing checks passed · no flight passed the flight rules`}
          </summary>
          <ul>
            {s.checklist.map((c) => (
              <li key={c.rule} className={c.passed ? '' : 'bad'}>
                <span className="mono">{c.rule}</span>
                <span>{c.detail}</span>
              </li>
            ))}
          </ul>
        </details>
      </div>

      <footer className="detail-foot">
        {isSplit && (
          <label className={`agree${agreed ? ' is-on' : ''}${needsAgreement && !agreed ? ' attention' : ''}`}>
            <input type="checkbox" checked={agreed} onChange={(e) => onAgree(e.target.checked)} />
            <span className="box" aria-hidden="true">
              <Check />
            </span>
            <span className="agree-text">The family agreed to this split{checks.map((c) => `, and ${c}`).join('')}.</span>
            <kbd>a</kbd>
          </label>
        )}
        {needsAgreement && !agreed && <p className="foot-error">Tick this once the family has agreed, then confirm.</p>}
        {error && (
          <p className="foot-error" role="alert">
            {error}
          </p>
        )}
        <button className="primary" disabled={busy || (isSplit && !agreed)} onClick={onConfirm}>
          <span>{busy ? 'Saving…' : s.suggestion ? `Confirm ${flights.map((f) => f.flight_no).join(' + ')}` : 'Confirm · handled by hand'}</span>
          {!busy && (
            <span className="kbd-pair" aria-hidden="true">
              <kbd>⌘</kbd>
              <kbd>↵</kbd>
            </span>
          )}
        </button>
        <p className="foot-note">Records your decision only. Book the flight in Southwest's system.</p>
      </footer>
    </aside>
  )
}
