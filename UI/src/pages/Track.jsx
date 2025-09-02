import { useEffect, useMemo, useState } from 'react'
import { Box, Button, Heading, Meter, Text } from 'grommet'
import API from '../api'
import BottomNav from '../components/BottomNav'
import Toast from '../components/Toast'
import HabitCard from '../components/HabitCard'
import { useNavigate } from 'react-router-dom'
import { localISODate } from '../lib/date'

export default function Track() {
  const nav = useNavigate()
  const [habits, setHabits] = useState([])
  const [summary, setSummary] = useState({ earned_today: 0, available_today: 0, progress: 0 })
  const [toast, setToast] = useState(null)
  const day = useMemo(() => localISODate(), [])

  async function load() {
    // fetch independently so one failure doesn’t block the other
    try {
      const h = await API.getHabits(day)
      setHabits(h.habits || [])
    } catch { setHabits([]) }

    try {
      const s = await API.getTodaySummary(day)
      setSummary({
        earned_today: s.earned_today || 0,
        available_today: s.available_today || 0,
        progress: s.progress || 0,
      })
    } catch { setSummary({ earned_today: 0, available_today: 0, progress: 0 }) }
  }

  useEffect(() => { load() }, [day])

  const onCompleted = () => {
    setToast('Nice! +pts')
     // after completion, refresh both list and summary
    load()
  }

  const onDeleted = (deletedId) => {
    // 1) optimistic removal
    setHabits(prev => prev.filter(h => h.id !== deletedId))
    setToast('Habit deleted')
    // 2) then refetch from server (keeps progress/denominator correct)
    load()
  }

  const pct = Math.max(0, Math.min(1, summary.progress))
  const pct100 = Math.round(pct * 100)

  return (
    <Box fill pad={{ bottom: '80px', horizontal: 'medium', top: 'medium' }} gap="medium">
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}

      <Heading level={3} margin="none">Track</Heading>

      {/* Progress Bar */}
      <Box gap="xxsmall">
        <Box direction="row" justify="between" align="center">
          <Text size="small" color="text-weak">Today</Text>
          <Text size="small" color="text-weak">
            {summary.earned_today.toFixed(1)} / {summary.available_today.toFixed(1)} pts ({pct100}%)
          </Text>
        </Box>
        <Meter values={[{ value: pct100 }]} thickness="small" background="light-3" />
      </Box>

      <Box gap="small">
        {habits.map(h => (
          <HabitCard
            key={h.id}
            habit={h}
            onCompleted={onCompleted}
            onDeleted={onDeleted}   // <<< pass handler down
          />
        ))}

        <Box direction="row" gap="small" margin={{ top: 'medium', bottom: 'large' }}>
          <Button primary label="Create Category" onClick={() => nav('/categories/new')} />
          <Button label="Add Habit" onClick={() => nav('/habits/new')} />
        </Box>
      </Box>

      <BottomNav />
    </Box>
  )
}
