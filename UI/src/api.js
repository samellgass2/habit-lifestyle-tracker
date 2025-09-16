// src/api.js
const BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/+$/, ''); // no trailing slash

// src/api.js (request helper)
async function req(path, { method = 'GET', json, body, headers, ...rest } = {}) {
  const url = `${BASE}${path.startsWith('/') ? path : `/${path}`}`

  const opts = {
    method,
    credentials: 'include',
    headers: { ...(headers || {}) },
    ...rest, // keep this last, but BEFORE we set body below
  }

  // Exactly one of: json | body
  if (json !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(json)            // <-- serialize payload
  } else if (body !== undefined) {
    opts.body = body                            // e.g., FormData/Blob
  }

  const res = await fetch(url, opts)

  // Robust parse
  const text = await res.text()
  let data
  try { data = text ? JSON.parse(text) : {} } catch { data = { raw: text } }

  if (!res.ok) {
    const msg = data?.error || data?.message || `HTTP ${res.status}`
    const err = new Error(msg)
    err.status = res.status
    err.data = data
    throw err
  }
  return data
}

const API = {
  me() {
    return req('/api/auth/me', { method: 'GET' });
  },
  login(username, password) {
    return req('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) });
  },
  logout() {
    return req('/api/auth/logout', { method: 'POST' });
  },
  createUser(u, p, p2) {
     return req('/api/users', {method:'POST', body: JSON.stringify({ username: u, password: p, password2: p2 }) });
  },
  createDayLog(payload) {
    return req('/api/daylogs', { method:'POST', body: JSON.stringify(payload) });
  },
  getDayLog(dayISO /* 'YYYY-MM-DD' */) {
    return req(`/api/daylogs?day=${encodeURIComponent(dayISO)}`, { method: 'GET' })
  },
  setTimezone(tz) {
    return req('/api/me/timezone', { method: 'POST', body: JSON.stringify({ timezone: tz }) })
  },
  getCalendar(month /* 'YYYY-MM' or undefined */) {
    const q = month ? `?month=${encodeURIComponent(month)}` : ''
    return req(`/api/calendar${q}`, { method: 'GET' })
  },
  getAISummary(scope = 'day') {
    return req(`/api/ai/summary?scope=${encodeURIComponent(scope)}`, { method: 'GET' })
  },
  getMyProfile() { return req('/api/me/profile', { method: 'GET' }) },
  updateMyProfile(payload) {
    return req('/api/me/profile', {
      method: 'PUT',
      json: payload,
    })
  },
  getHabits(dayISO) {
    return req(`/api/habits?when=${encodeURIComponent(dayISO)}`, { method: 'GET' })
  },
  completeHabit(id, payload={}) {
    return req(`/api/habits/${id}/complete`, { method: 'POST', json: payload })
  },
  createCategory(body) {
    return req('/api/categories', { method: 'POST', json: body })
  },
  createHabit(body) {
    return req('/api/habits', { method: 'POST', json: body })
  },
  listCategories() {
    return req('/api/categories', { method: 'GET' })
  },
  getPoints() {
    return req('/api/points', { method: 'GET' })
  },
  spendPoints(amount, note) {
    return req('/api/points/spend', { method: 'POST', json: { amount, note } })
  },
  getTodaySummary(dayISO) {
    return req(`/api/today/summary?day=${encodeURIComponent(dayISO)}`, { method: 'GET' })
  },
  deleteHabit(id) {
    return req(`/api/habits/${id}`, { method: 'DELETE' })
  },
  getPointsByCategory(period = 'week', anchor) {
    const qs = new URLSearchParams({ period, ...(anchor ? { anchor } : {}) })
    return req(`/api/analytics/points_by_category?${qs.toString()}`, { method: 'GET' })
  },
  getPointsOverTime(period = 'week', anchor) {
    const qs = new URLSearchParams({ period, ...(anchor ? { anchor } : {}) })
    return req(`/api/analytics/points_over_time?${qs.toString()}`, { method: 'GET' })
  },
  getRewards() { return req('/api/rewards', { method: 'GET' }) },
  createReward(payload) { return req('/api/rewards', { method: 'POST', body: JSON.stringify(payload) }) },
  updateReward(id, payload) { return req(`/api/rewards/${id}`, { method: 'PUT', body: JSON.stringify(payload) }) },
  deleteReward(id) { return req(`/api/rewards/${id}`, { method: 'DELETE' }) },
  purchaseReward(id, note) { return req(`/api/rewards/${id}/purchase`, { method: 'POST', body: JSON.stringify({ note }) }) },
  getRewardPurchases() { return req('/api/rewards/purchases', { method: 'GET' }) },
  getGratitudeCloud() {
    return req('/api/ai/gratitude_cloud')
  },
  getMotivation() {
    return req('/api/ai/motivation');
  },
  refreshMotivation() {
    try {
      return req('/api/ai/motivation/refresh', { method: 'POST' });
    } catch (e) {
      // Bubble up structured 429 info
      if (e.status === 429 && e.body?.retry_seconds) {
        e.code = 'too_soon';
      }
      throw e;
    }
  }

  // Example for your future endpoints:
  // createUser(username, password) {
  //   return req('/api/users', { method: 'POST', body: JSON.stringify({ username, password }) });
  // },
  // dbPing() {
  //   return req('/api/db/ping', { method: 'GET' });
  // },
};

export default API;
