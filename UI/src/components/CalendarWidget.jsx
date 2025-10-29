// src/components/CalendarWidget.jsx
import { useEffect, useMemo, useState } from 'react'
import { Box, Text, CheckBox } from 'grommet'
import API from '../api'
import { moodEmoji, dayBg } from '../lib/mood'
import { useNavigate } from 'react-router-dom'
import { localISODate } from '../lib/date'


const weekdayLabels = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']

function parseLocal(dateISO) {
  const [y,m,d] = dateISO.split('-').map(Number)
  return new Date(y, m - 1, d)      // <-- local midnight
}
function localDOW(dateISO) {
  return parseLocal(dateISO).getDay() // 0..6, Sun..Sat
}

const CELL_GAP = '8px'

function DayCell({ dateISO, completed, mood, onClick }) {
  const dayNum = parseInt(dateISO.slice(-2), 10)
  return (
    <Box
      round="xsmall"
      align="center"
      justify="center"
      style={{
        aspectRatio: '1 / 1',
        width: '100%',
        backgroundColor: completed ? '#e6f7ea' : '#f0f0f0', // ✅ light green vs gray
      }}
      pad="xsmall"
      onClick={() => onClick(dateISO)}
    >
      <Text size="small" color="text-weak" margin={{ bottom: 'xxsmall' }}>
        {dayNum}
      </Text>
      <Text size="small">{mood ? moodEmoji[mood] : ''}</Text>
    </Box>
  )
}


function MonthGrid({ days }) {
  // 7 columns, rows auto; add blanks for first weekday
  const firstDow = useMemo(() => localDOW(days[0].date), [days])
  const blanks = Array.from({ length: firstDow })
  const nav = useNavigate()
  function onDayClickMonth(dayISO) {
    nav('/reflect/daily', {
      state: {
        day: dayISO,            // 'YYYY-MM-DD' (LOCAL)
        historic: dayISO !== localISODate(),
      }
    })
  }

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
      <Box
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(7, 1fr)',
          gap: CELL_GAP,
        }}
      >
        {blanks.map((_, i) => <Box key={`b${i}`} />)}
        {days.map(d => (
          <DayCell key={d.date} {...d} dateISO={d.date} onClick={onDayClickMonth}/>
        ))}
      </Box>
    </Box>
  )
}

function WeekStrip({ week }) {
  const byDow = [...week].sort((a,b) => localDOW(a.date) - localDOW(b.date))
  const nav = useNavigate()
  function onDayClickWeek(dayISO) {
      nav('/reflect/daily', {
        state: {
          day: dayISO,            // 'YYYY-MM-DD' (LOCAL)
          historic: dayISO !== localISODate(),
        }
      })
    }
  return (
    <Box style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: CELL_GAP }}>
      {byDow.map(d => (
        <Box key={d.date}>
          <Box align="center" margin={{ bottom: 'xxsmall' }}>
            <Text size="small" color="text-weak">
              {weekdayLabels[localDOW(d.date)]}
            </Text>
          </Box>
          <DayCell {...d} dateISO={d.date} onClick={onDayClickWeek}/>
        </Box>
      ))}
    </Box>
  )
}


export default function CalendarWidget() {
  const [data, setData] = useState(null)
  const [monthMode, setMonthMode] = useState(false) // false=week, true=month

  useEffect(() => {
    (async () => {
      const res = await API.getCalendar()
      setData(res)
    })()
  }, [])

  if (!data) return null

  return (
    <Box pad="medium" round="small" border={{ color:'border', size:'xsmall' }} background="background">
      <Box direction="row" justify="between" align="center" margin={{ bottom: 'small' }}>
        <Text weight={700}>{'Tracker Usage (' + (monthMode ? 'This Month' : 'This Week') + ')'}</Text>
        <CheckBox
          toggle
          checked={monthMode}
          onChange={e => setMonthMode(e.target.checked)}
          label={<Text size="small">Month</Text>}
        />
      </Box>

      {monthMode ? <MonthGrid days={data.days} /> : <WeekStrip week={data.week} />}
    </Box>
  )
}
