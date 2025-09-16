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

  const onCompleted = (points) => {
    setToast('Nice! +'+(points ? points.toString() : '')+'pts')
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

      <Box height="30px" />
      <Heading level={1} margin="none">Track</Heading>

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

      {/* Make this a comfortable gap for cards */}
      <Box gap="medium">
        {habits.map(h => (
          <HabitCard
            key={h.id}
            habit={h}
            onCompleted={onCompleted}
            onDeleted={onDeleted}
          />
        ))}

        {/* Responsive action buttons */}
        <Box
          direction="row"
          wrap
          gap="small"
          margin={{ top: 'medium', bottom: 'large' }}
        >
          <Box basis="1/2" flex>
            <Button
              primary
              fill="horizontal"
              size="large"
              label="Create Category"
              onClick={() => nav('/categories/new')}
            />
          </Box>
          <Box basis="1/2" flex>
            <Button
              fill="horizontal"
              size="large"
              label="Add Habit"
              onClick={() => nav('/habits/new')}
            />
          </Box>
          <Box height="250px" />
        </Box>
      </Box>
      
      <BottomNav />
    </Box>
  )
}
