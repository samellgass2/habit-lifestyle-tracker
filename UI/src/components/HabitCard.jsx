// src/components/HabitCard.jsx
import { useState } from 'react'
import { Box, Button, Text, Layer } from 'grommet'
import { More } from 'grommet-icons'
import API from '../api'
import SliderWithTrack from './SlideWithTrack'

export default function HabitCard({ habit, onCompleted, onDeleted }) {
  const [busy, setBusy] = useState(false)
  const [showMenu, setShowMenu] = useState(false)
  const [mins, setMins] = useState(habit.time_minutes || 30)
  const [pct, setPct]   = useState(habit.percent_target || 100)

  const color = habit.category?.color || '#E5E7EB'
  const emoji = habit.category?.emoji || '✅'
  const disabled = habit.completed_today || busy

  const complete = async () => {
    setBusy(true)
    try {
      let payload = {}
      if (habit.points_mode === 'time') payload.time_minutes = mins
      if (habit.points_mode === 'percent') payload.percent_value = pct
      const res = await API.completeHabit(habit.id, payload)
      onCompleted?.(res.points_awarded)
    } finally { setBusy(false) }
  }

  const requestDelete = async () => {
    setBusy(true)
    try {
      await API.deleteHabit(habit.id)
      setShowMenu(false)
      onDeleted?.(habit.id)
    } catch (e) {
      // optional toast at parent
      setShowMenu(false)
    } finally { setBusy(false) }
  }

  const label = `Complete (+${habit.potential_points} pts)`

  return (
    <Box round="small" border={{ color:'border' }} pad="small" gap="small" style={{ position:'relative' }}>
      {/* header row */}
      <Box direction="row" gap="small" align="center" justify="between">
        <Box direction="row" gap="small" align="center">
          <Box width="8px" background={color} round="xsmall" />
          <Text>{emoji} {habit.name}</Text>
          {habit.type === 'one-off' && (
            <Text size="small" color="text-weak">(for {habit.date_local})</Text>
          )}
          {habit.completed_today && <Text size="xsmall" color="status-ok">Done</Text>}
        </Box>
        <Button icon={<More />} onClick={() => setShowMenu(true)} plain />
      </Box>

      {/* body */}
      {habit.points_mode === 'time' && (
        <Box gap="xsmall">
          <Box direction="row" gap="xsmall">
            {[15,30,45,60].map(v => (
              <Button key={v} label={`${v}m`} onClick={() => setMins(v)} disabled={disabled} primary={mins===v} />
            ))}
          </Box>
        </Box>
      )}
      {habit.points_mode === 'percent' && (
        <Box gap="xsmall">
          <SliderWithTrack min={0} max={100} step={5} value={pct} onChange={e => setPct(Number(e.target.value))} disabled={disabled}/>
          <Box direction="row" justify="between">
            <Text size="xsmall">0%</Text><Text size="xsmall">25%</Text><Text size="xsmall">50%</Text>
            <Text size="xsmall">75%</Text><Text size="xsmall">100%</Text>
          </Box>
        </Box>
      )}

      <Button primary label={busy ? 'Completing…' : label} onClick={complete} disabled={disabled} />

      {/* delete modal */}
      {showMenu && (
        <Layer
          position="center"
          onEsc={() => setShowMenu(false)}
          onClickOutside={() => setShowMenu(false)}
          modal
        >
          <Box pad="medium" gap="small" width="320px">
            <Text weight="bold">Habit options</Text>
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
