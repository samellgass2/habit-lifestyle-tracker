// src/api.js
const BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/+$/, ''); // no trailing slash

async function req(path, options = {}) {
  const url = `${BASE}${path.startsWith('/') ? path : `/${path}`}`;
  const res = await fetch(url, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });

  // Try to parse JSON either way
  let body;
  try { body = await res.json(); } catch { body = null; }

  if (!res.ok) {
    const msg = (body && (body.error || body.message)) || `HTTP ${res.status}`;
    const err = new Error(msg);
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return body;
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
