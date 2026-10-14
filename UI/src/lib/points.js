// Mirror of the server's points math (api-server habit_tracker/utils.py,
// compute_points / potential_points_for_habit): 1 task = 100 points,
// 30 minutes = 100, 10% = 100; x challenge x importance x base; focus doubles.
const CHALLENGE_MULT = { automatic: 0.75, easy: 1.0, difficult: 1.25, hard: 1.5, daunting: 2.0 }
const IMPORTANCE_MULT = { 1: 1.0, 2: 1.5, 3: 2.0 }

export function computePoints(pointsMode, baseValue, challenge, importance,
  { time_minutes = null, percent_value = null, is_focused = false, instances = 1 } = {}) {
  const base = Number(baseValue ?? 1) || 1
  const c = CHALLENGE_MULT[challenge] ?? 1
  const i = IMPORTANCE_MULT[Number(importance)] ?? 1
  let payload
  if (pointsMode === 'tasks') payload = 100
  else if (pointsMode === 'time') payload = 100 * (Math.max(0, Number(time_minutes) || 0) / 30)
  else payload = 10 * Math.max(0, Math.min(100, Number(percent_value) || 0))
  if (is_focused) payload = Math.round(payload * 2 * 100) / 100
  return Math.round(((base * c * i * payload) / (instances || 1)) * 100) / 100
}

export function potentialPointsForHabit(pointsMode, baseValue, challenge, importance,
  { time_target = null, percent_target = null, is_focused = false } = {}) {
  if (pointsMode === 'tasks') return computePoints('tasks', baseValue, challenge, importance, { is_focused })
  if (pointsMode === 'time') return computePoints('time', baseValue, challenge, importance, { time_minutes: time_target || 0, is_focused })
  return computePoints('percent', baseValue, challenge, importance, { percent_value: percent_target || 0, is_focused })
}
