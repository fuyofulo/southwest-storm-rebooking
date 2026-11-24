// Times in the data are local airport times with no time zone: format them as written.

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export function when(ts) {
  if (!ts) return '—'
  const [d, t = ''] = ts.split('T')
  const [y, m, day] = d.split('-').map(Number)
  const weekday = DAYS[new Date(y, m - 1, day).getDay()]
  return `${weekday} ${day} ${MONTHS[m - 1]} ${t.slice(0, 5)}`.trim()
}

export const STATUS_LABEL = {
  ready_to_confirm: 'Whole party side by side on one flight',
  split_party_confirm: 'Split party: family must agree',
  no_option_found: 'No flight met the rules',
}

// One line per flight: "WN1046 19 Nov 07:20 ×3" (the count only for a split).
export function suggestionLines(s) {
  if (!s.suggestion) return ['No flight met the rules']
  const split = s.suggestion.flights.length > 1
  return s.suggestion.flights.map(
    (f) => `${f.flight_no} ${when(f.departure_datetime).replace(/^\w{3} /, '')}${split ? ` ×${f.passengers}` : ''}`,
  )
}
