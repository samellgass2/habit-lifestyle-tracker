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
    // payload may include:
    // { day: 'YYYY-MM-DD', time_minutes, percent_value }
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
  },
  getCompletedHabits(opts = {}) {
    // opts may include { since, until, limit, offset }
    const qs = new URLSearchParams(
      Object.fromEntries(Object.entries(opts).filter(([, v]) => v !== undefined && v !== null))
    )
    const q = qs.toString() ? `?${qs.toString()}` : ''
    return req(`/api/track/completed${q}`, { method: 'GET' })
  },
  generateHabitPreview(body) {
    // body: { category_id?: number, user_input?: string }
    return req('/api/habits/ai/preview', { method: 'POST', json: body })
  },
  getFocus() {
    return req('/api/focus', { method: 'GET' })
  },
  updateHabit(id, body) {
    return req(`/api/habits/${id}`, { method: 'PUT', json: body })
  },
  getHabit: (id) => req(`/api/habits/${id}`),
  getCalendarProgress(year, month) {
    return req(`/api/calendar/progress?year=${year}&month=${month}`)
  },

  // --- Friends / social graph ---

  /**
   * Search for users by substring of name.
   * Returns: { users: [ { id, name, emoji, color, friendship? } ] }
   */
  searchUsers(q) {
    const qs = new URLSearchParams({ q })
    return req(`/api/users/search?${qs.toString()}`, { method: 'GET' })
  },

  /**
   * List friendships for the current user.
   * Optional status: 'pending' | 'accepted' | 'rejected'
   * Returns: { friendships: [ { id, status, direction, other_user_id, ... } ] }
   */
  getFriendships(status) {
    const params = new URLSearchParams()
    if (status) params.set('status', status)
    const q = params.toString() ? `?${params.toString()}` : ''
    return req(`/api/friends${q}`, { method: 'GET' })
  },

  /**
   * Create a friend request to target user_id, optional message.
   * Returns: { friendship: {...} }
   */
  createFriendRequest(userId, message) {
    return req('/api/friends', {
      method: 'POST',
      json: { user_id: userId, message: message ?? null },
    })
  },

  /**
   * Update a friendship (currently: accept / reject).
   * status must be 'accepted' or 'rejected'.
   */
  updateFriendship(friendshipId, status) {
    return req(`/api/friends/${friendshipId}`, {
      method: 'PATCH',
      json: { status },
    })
  },

  /**
   * Delete a friendship (cancel pending or unfriend).
   */
  deleteFriendship(friendshipId) {
    return req(`/api/friends/${friendshipId}`, { method: 'DELETE' })
  },

  getUserSummaries(userIds) {
    return req('/api/users/summaries', {
      method: 'POST',
      json: { user_ids: userIds },
    })
  },

  getUsersFeed(userIds, offset = 0, limit = 20) {
    return req('/api/users/feed', {
      method: 'POST',
      json: {
        user_ids: userIds,
        offset: offset,
        limit: limit,
      }
    })
  },

  // --- Feed reactions & comments ---

  getFeedReactions(feedKind, feedItemId) {
    const params = new URLSearchParams({
      feed_kind: feedKind,
      feed_item_id: String(feedItemId),
    })
    return req(`/api/feed/reactions?${params.toString()}`, {
      method: 'GET',
    })
  },

  postFeedReaction(feedKind, feedItemId, reaction) {
    return req('/api/feed/react', {
      method: 'POST',
      json: {
        feed_kind: feedKind,
        feed_item_id: feedItemId,
        reaction,
      },
    })
  },

  getFeedComments(feedKind, feedItemId, limit) {
    const params = new URLSearchParams({
      feed_kind: feedKind,
      feed_item_id: String(feedItemId),
    })
    if (limit != null) {
      params.set('limit', String(limit))
    }
    return req(`/api/feed/comments?${params.toString()}`, {
      method: 'GET',
    })
  },

  postFeedComment(feedKind, feedItemId, comment) {
    return req('/api/feed/comments', {
      method: 'POST',
      json: {
        feed_kind: feedKind,
        feed_item_id: feedItemId,
        comment,
      },
    })
  },

  getInbox() {
    return req('/api/social/inbox', { method: 'GET' })
  },

  /**
   * Mark inbox items as seen.
   * payload: { reaction_ids?: number[], comment_ids?: number[] }
   */
  markInboxSeen(payload) {
    return req('/api/social/inbox/seen', {
      method: 'POST',
      json: payload || { reaction_ids: [], comment_ids: [] },
    })
  },

  getFriendCategories(friendId) {
    return req(`/api/friends/${friendId}/categories`, { method: 'GET' })
  },

  // Pending actions (send habits/rewards to friends)
  getPendingActions(direction = 'outbound', type) {
    const params = new URLSearchParams({ direction })
    if (type) params.set('type', type)
    const q = params.toString() ? `?${params.toString()}` : ''
    return req(`/api/pending/actions${q}`, { method: 'GET' })
  },

  createPendingAction(body) {
    return req('/api/pending/actions', { method: 'POST', json: body })
  },

  updatePendingAction(type, id, body) {
    return req(`/api/pending/actions/${type}/${id}`, { method: 'PUT', json: body })
  },

  respondPendingAction(type, id, action) {
    return req(`/api/pending/actions/${type}/${id}/respond`, {
      method: 'POST',
      json: { action },
    })
  },
  

  // Example for your future endpoints:
  // createUser(username, password) {
  //   return req('/api/users', { method: 'POST', body: JSON.stringify({ username, password }) });
  // },
  // dbPing() {
  //   return req('/api/db/ping', { method: 'GET' });
  // },
};

export default API;
