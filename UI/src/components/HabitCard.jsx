import { useMemo, useState } from 'react'
import { Box, Button, Text, Layer } from 'grommet'
import { More } from 'grommet-icons'
import API from '../api'
import SliderWithTrack from './SlideWithTrack'

function round5(n){ return Math.max(5, Math.round(n / 5) * 5) }

// --- helpers: hex → rgb + contrast-aware text color ---
function hexToRgb(hex) {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex || '')
  if (!m) return { r: 229, g: 231, b: 235 } // #E5E7EB default
  return { r: parseInt(m[1], 16), g: parseInt(m[2], 16), b: parseInt(m[3], 16) }
}
function textOn(hex) {
  const { r, g, b } = hexToRgb(hex)
  const srgb = [r, g, b].map(v => {
    const c = v / 255
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
  })
  const L = 0.2126 * srgb[0] + 0.7152 * srgb[1] + 0.0722 * srgb[2]
  return L > 0.6 ? '#111827' /* dark text */ : '#F9FAFB' /* near-white */
}

export default function HabitCard({ habit, onCompleted, onDeleted }) {
  const [busy, setBusy] = useState(false)
  const [showMenu, setShowMenu] = useState(false)

  const timeTarget = habit.time_minutes || 30
  const pctTarget  = habit.percent_target || 100

  const [mins, setMins] = useState(timeTarget)
  const [pct,  setPct]  = useState(pctTarget)

  const timeOptions = useMemo(() => {
    if (habit.points_mode !== 'time') return []
    const mults = [0.5, 1, 1.5, 2]
    const opts = mults.map(m => round5(timeTarget * m))
    return Array.from(new Set(opts))
  }, [habit.points_mode, timeTarget])

  const disabled = habit.completed_today || busy

  const complete = async () => {
    setBusy(true)
    try {
      let payload = {}
      if (habit.points_mode === 'time')    payload.time_minutes = mins
      if (habit.points_mode === 'percent') payload.percent_value = pct
      const res = await API.completeHabit(habit.id, payload)
      onCompleted?.(res.points_awarded)
    } finally { setBusy(false) }
  }

  // compute shown points proportionally
  const shownPoints = useMemo(() => {
    const pp = Number(habit.potential_points || 0)
    if (habit.points_mode === 'time') {
      const ratio = Math.max(0, mins) / Math.max(1, timeTarget)
      return Math.round(pp * ratio * 100) / 100
    }
    if (habit.points_mode === 'percent') {
      const ratio = Math.max(0, pct) / Math.max(1, pctTarget)
      return Math.round(pp * ratio * 100) / 100
    }
    return pp
  }, [habit.points_mode, habit.potential_points, mins, pct, timeTarget, pctTarget])

  const label = `Complete (+${shownPoints} pts)`

  const color = habit.category?.color || '#E5E7EB'
  const emoji = habit.category?.emoji || '✅'
  const fg = useMemo(() => textOn(color), [color])  // text color for contrast

  const requestDelete = async () => {
    setBusy(true)
    try {
      await API.deleteHabit(habit.id)
      setShowMenu(false)
      onDeleted?.(habit.id)
    } finally { setBusy(false) }
  }

  return (
    <Box
      round="medium"
      pad={{ horizontal:'medium', vertical:'large' }}
      gap="medium"
      margin={{ vertical:'medium' }}
      // colored backdrop + subtle veil for legibility
      style={{
        background: color,
        minHeight: '200px',
        boxShadow: 'inset 0 0 0 9999px rgba(255,255,255,0.06)',
      }}
      border={{ color: 'rgba(0,0,0,0.08)' }}
    >
      {/* header */}
      <Box direction="row" align="center" justify="between" flex={false}>
        <Box direction="row" gap="small" align="center" wrap>
          {/* slim color marker still looks nice */}
          <Box width="8px" background={color} round="xsmall" />
          <Text size="large" style={{ color: fg }}>{emoji} {habit.name}</Text>
          {habit.type === 'one-off' && (
            <Text size="small" style={{ color: fg, opacity: 0.8 }}>(for {habit.date_local})</Text>
          )}
          {habit.completed_today && <Text size="xsmall" style={{ color: fg }}>Done</Text>}
        </Box>
        <Button icon={<More color={fg} />} onClick={() => setShowMenu(true)} plain />
      </Box>

      {/* body */}
      {habit.points_mode === 'time' && (
        <Box gap="small" flex={false}>
          <Box direction="row" gap="xsmall" justify="between" wrap={false}>
            {timeOptions.map(v => (
              <Button
                key={v}
                onClick={() => setMins(v)}
                disabled={disabled}
                primary={mins === v}
                style={{
                  flex: '1 1 25%',
                  minWidth: 0,
                  padding: '10px 0',
                  display: 'flex',
                  borderRadius: '6px',
                  border: '1px solid rgba(0,0,0,0.18)',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: mins === v ? 'rgba(0,0,0,0.12)' : 'rgba(255,255,255,0.22)',
                  color: fg,
                }}
              >
                <Text style={{ color: fg }}>{v}m</Text>
              </Button>
            ))}
          </Box>
          <Text size="xsmall" style={{ color: fg, opacity: 0.85 }} margin={{ top: 'xsmall' }}>
            Target: {timeTarget}m
          </Text>
        </Box>
      )}

      {habit.points_mode === 'percent' && (
        <Box gap="small" flex={false}>
          <SliderWithTrack
            min={0} max={100} step={5}
            value={pct}
            onChange={e => setPct(Number(e.target.value))}
            disabled={disabled}
          />
          <Box direction="row" justify="between">
            <Text size="xsmall" style={{ color: fg }}>0%</Text>
            <Text size="xsmall" style={{ color: fg }}>25%</Text>
            <Text size="xsmall" style={{ color: fg }}>50%</Text>
            <Text size="xsmall" style={{ color: fg }}>75%</Text>
            <Text size="xsmall" style={{ color: fg }}>100%</Text>
          </Box>
          <Text size="xsmall" style={{ color: fg, opacity: 0.85 }} margin={{ top: 'xsmall' }}>
            Target: {pctTarget}%
          </Text>
        </Box>
      )}

      <Box flex={false}>
        <Button
          primary
          label={busy ? 'Completing…' : label}
          onClick={complete}
          disabled={disabled}
          // keep the CTA readable on colored backgrounds
          style={{
            color: '#fff',
            background: 'rgba(124,58,237,0.95)', // brand-ish
          }}
        />
      </Box>

      {showMenu && (
        <Layer
          position="center"
          onEsc={() => setShowMenu(false)}
          onClickOutside={() => setShowMenu(false)}
          modal
          responsive={false}
        >
          <Box
            pad="medium"
            gap="small"
            width="90vw"
            style={{ maxWidth: 360 }}
            round="small"
            elevation="small"
            background="background-contrast"
          >
            <Text weight="bold">{"Habit options for '" + habit.name + "'"} </Text>
            <Button
              label="Delete habit"
              color="status-critical"
              onClick={requestDelete}
              disabled={busy}
              primary
            />
            <Button label="Cancel" onClick={() => setShowMenu(false)} />
          </Box>
        </Layer>
      )}
    </Box>
  )
}
