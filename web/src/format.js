// Times in the data are local airport times with no time zone: format them as written.

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function parts(ts) {
  const [d, t = ''] = ts.split('T')
  const [y, m, day] = d.split('-').map(Number)
  return { weekday: DAYS[new Date(y, m - 1, day).getDay()], day, month: MONTHS[m - 1], time: t.slice(0, 5) }
}

/** "Thu 19 Nov" */
export function day(ts) {
  if (!ts) return '—'
  const p = parts(ts)
  return `${p.weekday} ${p.day} ${p.month}`
}

/** "07:20" */
export function time(ts) {
  return ts ? parts(ts).time : '—'
}

/** "Thu 19 Nov · 07:20" */
export function when(ts) {
  return ts ? `${day(ts)} · ${time(ts)}` : '—'
}

/** "19 Nov 07:20" (compact, for the list) */
export function short(ts) {
  if (!ts) return '—'
  const p = parts(ts)
  return `${p.day} ${p.month} ${p.time}`
}

export function usd(value) {
  const n = Number(value)
  return Number.isFinite(n) ? `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'
}

export const STATUSES = ['ready_to_confirm', 'split_party_confirm', 'no_option_found']

export const STATUS_HELP = {
  ready_to_confirm: 'The whole party side by side on one flight',
  split_party_confirm: 'Split across different flights: the family must agree',
  no_option_found: 'No flight met the rules',
}

export function matches(s, query) {
  const q = query.trim().toLowerCase()
  if (!q) return true
  const hay = [s.booking_id, s.lead_passenger_name, s.origin_airport, s.destination_airport, `${s.origin_airport}-${s.destination_airport}`]
    .concat((s.suggestion?.flights || []).map((f) => f.flight_no))
    .join(' ')
    .toLowerCase()
  return q.split(/\s+/).every((word) => hay.includes(word))
}
