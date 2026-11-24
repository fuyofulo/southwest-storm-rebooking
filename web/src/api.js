// Talks to the rebooking service (FastAPI) through the /api proxy in vite.config.js.

const LIST_TIMEOUT_MS = 240_000 // the first load may ask the model about every booking not yet cached
const CONFIRM_TIMEOUT_MS = 60_000

export class ServiceError extends Error {
  constructor(message, status = null) {
    super(message)
    this.status = status
  }
}

async function call(path, { timeout, ...init } = {}) {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeout)
  let res
  try {
    res = await fetch(`/api${path}`, { ...init, signal: ctrl.signal })
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new ServiceError(`The rebooking service did not answer within ${Math.round(timeout / 1000)} seconds.`)
    }
    throw new ServiceError('The rebooking service is not reachable.')
  } finally {
    clearTimeout(timer)
  }
  let body = null
  try {
    body = await res.json()
  } catch {
    // the proxy answers with HTML or nothing when the service is down
  }
  if (!res.ok) {
    if (res.status >= 500 && !body) throw new ServiceError('The rebooking service is not reachable.', res.status)
    const detail = body && typeof body.detail === 'string' ? body.detail : `HTTP ${res.status}`
    throw new ServiceError(detail, res.status)
  }
  if (body === null) throw new ServiceError('The rebooking service sent an empty answer.', res.status)
  return body
}

export function fetchWaiting() {
  return call('/suggestions', { timeout: LIST_TIMEOUT_MS })
}

export function fetchConfirmed() {
  return call('/confirmations', { timeout: CONFIRM_TIMEOUT_MS })
}

export function confirmBooking(bookingId, confirmedBy, optionId) {
  return call(`/bookings/${encodeURIComponent(bookingId)}/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirmed_by: confirmedBy, option_id: optionId }),
    timeout: CONFIRM_TIMEOUT_MS,
  })
}
