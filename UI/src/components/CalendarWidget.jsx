// src/components/CalendarWidget.jsx
import { useEffect, useMemo, useState, useCallback } from 'react'
import { Box, Text, CheckBox } from 'grommet'
import { useNavigate } from 'react-router-dom'
import API from '../api'
import { moodEmoji } from '../lib/mood'
import { localISODate } from '../lib/date'

// ---------- helpers ----------
const weekdayLabels = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']
const CELL_GAP = '8px'

function parseLocal(dateISO) {
  if (!dateISO || typeof dateISO !== 'string') return new Date()
  const [y, m, d] = dateISO.split('-').map(Number)
  return new Date(y || 1970, (m || 1) - 1, d || 1) // local midnight
}
function localDOW(dateISO) {
  return parseLocal(dateISO).getDay() // 0..6, Sun..Sat
}

// ---- coloring for progress mode ----
function pctColor(pct) {
  if (!Number.isFinite(pct)) return '#f3f4f6' // gray-100 for no data
  if (pct >= 0.80) return '#d1fae5' // green-100
  if (pct >= 0.50) return '#fef9c3' // yellow-100
  if (pct >= 0.25) return '#fee2e2' // red-100 (light)
  return '#fecaca'                  // red-200
}

function DayCell({ progress, dateISO, percent, completed, mood, onClick }) {
  const dayNum = dateISO ? parseInt(dateISO.slice(-2), 10) : ''
  const isProgress = !!progress

  let bg
  let inner
  if (isProgress) {
    const pct = (typeof percent === 'number') ? Math.max(0, Math.min(1, percent)) : NaN
    bg = pctColor(pct)
    inner = Number.isFinite(pct) ? `${Math.round(pct * 100)}%` : '--%'
  } else {
    // legacy usage view (mood/checkbox)
    bg = completed ? '#e6f7ea' : '#f0f0f0'
    if (mood !== null && mood !== undefined) inner = moodEmoji[mood] || ''
    else if (completed) inner = '✅'
    else inner = ''
  }

  return (
    <Box
      round="xsmall"
      align="center"
      justify="center"
      style={{ aspectRatio: '1 / 1', width: '100%', backgroundColor: bg }}
      pad="xsmall"
      onClick={() => onClick?.(dateISO)}
      title={dateISO}
    >
      <Text size="small" color="text-weak" margin={{ bottom: 'xxsmall' }}>{dayNum}</Text>
      <Text size="small">{inner}</Text>
    </Box>
  )
}

function MonthGrid({ progress, days, onPick }) {
  const firstIso = (days && days[0]?.date) || localISODate()
  const firstDow = useMemo(() => localDOW(firstIso), [firstIso])
  const blanks = Array.from({ length: firstDow })
  const nav = useNavigate()

  const onDayClickMonth = useCallback((dayISO) => {
    if (onPick) return onPick(dayISO)
    // legacy navigation fallback (kept for back-compat with reflections)
    nav('/reflect/daily', {
      state: { day: dayISO, historic: dayISO !== localISODate() }
    })
  }, [nav, onPick])

  return (
    <Box gap="small">
      {/* headers */}
      <Box direction="row" gap="small">
        {weekdayLabels.map(w => (
          <Box key={w} flex align="center">
            <Text size="small" weight={600} color="text-weak">{w}</Text>
          </Box>
        ))}
      </Box>

      {/* calendar grid */}
      <Box style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: CELL_GAP }}>
        {blanks.map((_, i) => <Box key={`b${i}`} />)}
        {(days || []).map(d => (
          <DayCell
            key={d.date}
            progress={progress}
            dateISO={d.date}
            percent={d.percent}
            completed={d.completed}
            mood={d.mood}
            onClick={onDayClickMonth}
          />
        ))}
      </Box>
    </Box>
  )
}

function WeekStrip({ progress, week, onPick }) {
  const byDow = [...(week || [])].sort((a, b) => localDOW(a.date) - localDOW(b.date))
  const nav = useNavigate()

  const onDayClickWeek = useCallback((dayISO) => {
    if (onPick) return onPick(dayISO)
    nav('/reflect/daily', {
      state: { day: dayISO, historic: dayISO !== localISODate() }
    })
  }, [nav, onPick])

  return (
    <Box style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: CELL_GAP }}>
      {byDow.map(d => (
        <Box key={d.date}>
          <Box align="center" margin={{ bottom: 'xxsmall' }}>
            <Text size="small" color="text-weak">{weekdayLabels[localDOW(d.date)]}</Text>
          </Box>
          <DayCell
            progress={progress}
            dateISO={d.date}
            percent={d.percent}
            completed={d.completed}
            mood={d.mood}
            onClick={onDayClickWeek}
          />
        </Box>
      ))}
    </Box>
  )
}

/**
 * CalendarWidget
 * Props:
 *   - mode?: string (default tracker). If progress → calls /api/calendar/progress and shows percent cells.
 *   - onPick?: (dateISO: string) => void. If provided, clicking a cell will call onPick(dateISO).
 *     Otherwise legacy navigation occurs to /reflect/daily.
 *
 * Backward-compatible:
 *   - When progress=false, uses the original /api/calendar with {completed,mood}.
 *   - When progress=true, uses /api/calendar/progress with {percent}.
 */
export default function CalendarWidget({ mode = "tracker", onPick }) {
  const [data, setData] = useState(null)
  const [monthMode, setMonthMode] = useState(false) // false=week, true=month
  const progressMode = mode == "progress"
  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        // Determine current local month/year for progress mode (optional)
        const todayISO = localISODate()
        const [yy, mm] = todayISO.split('-').map(Number)

        const res = progressMode
          ? await API.getCalendarProgress(yy,mm) // NEW
          : await API.getCalendar()                                // legacy
        if (!alive) return
        setData(res)
      } catch (e) {
        if (!alive) return
        // Fallback: set minimal structure to avoid blank UI
        setData({ month: '', days: [], week: [] })
      }
    })()
    return () => { alive = false }
  }, [progressMode])

  if (!data) return null

  return (
    <Box pad="medium" round="small" border={{ color: 'border', size: 'xsmall' }} background="background">
      <Box direction="row" justify="between" align="center" margin={{ bottom: 'small' }}>
        <Text weight={700}>
          {progressMode ? 'Daily Progress' : 'Tracker Usage'} ({monthMode ? 'This Month' : 'This Week'})
        </Text>
        <CheckBox
          toggle
          checked={monthMode}
          onChange={e => setMonthMode(e.target.checked)}
          label={<Text size="small">Month</Text>}
        />
      </Box>

      {monthMode
        ? <MonthGrid progress={progressMode} days={data.days || []} onPick={onPick} />
        : <WeekStrip  progress={progressMode} week={data.week || []} onPick={onPick} />}
    </Box>
  )
}
