import { useEffect, useMemo, useState } from 'react'
import { Box, Heading, Text, Button } from 'grommet'
import { FormPreviousLink, StatusGoodSmall } from 'grommet-icons'
import { useNavigate } from 'react-router-dom'
import BottomNav from '../components/BottomNav'
import API from '../api'

const toLocalDate = (yyyy_mm_dd) => new Date(`${yyyy_mm_dd}T00:00:00`)
function dayLabel(yyyy_mm_dd) {
  if (!yyyy_mm_dd) return ''
  const d = toLocalDate(yyyy_mm_dd)
  const today = new Date()
  const yest = new Date(); yest.setDate(today.getDate() - 1)
  const key = (dt) => dt.toISOString().slice(0,10)
  if (key(d) === key(today)) return 'Today'
  if (key(d) === key(yest))  return 'Yesterday'
  return d.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })
}

function ColorDot({ color }) {
  const c = color || '#E5E7EB'
  return <Box width="8px" height="8px" round="full" background={c} />
}

export default function TrackHistory() {
  const nav = useNavigate()
  const [rows, setRows] = useState([])

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const r = await API.getCompletedHabits()
        if (alive) setRows(r?.items || [])
      } catch {
        if (alive) setRows([])
      }
    })()
    return () => { alive = false }
  }, [])

  const groups = useMemo(() => {
    const map = new Map()
    for (const r of rows) {
      const key = (r.day_local || '').slice(0, 10)
      if (!map.has(key)) map.set(key, [])
      map.get(key).push(r)
    }
    return Array.from(map.entries()).sort((a,b) => b[0].localeCompare(a[0]))
  }, [rows])

  return (
    <Box fill direction="column">
      <Box flex overflow="auto" style={{ minHeight: 0 }} pad={{ horizontal: 'medium', top: 'xlarge' }} gap="medium">
        <Box height="80px" />
        <Box direction="row" justify="between" align="center">
          <Heading level={3} margin="none">Completed tasks</Heading>
          <Button
            icon={<FormPreviousLink size="large" />}  // bigger arrow
            onClick={() => nav(-1)}
            plain
            pad="xsmall"  // increases tap target without adding borders
          />
        </Box>

        {groups.length === 0 && <Text color="text-weak">No completed tasks yet.</Text>}

        {groups.length === 0 && <Text color="text-weak">No completed tasks yet.</Text>}

        {groups.map(([day, items]) => (
          <Box key={day} as="section" gap="xsmall" margin={{ top: 'medium' }} flex={false}>
            <Heading level={4} size="small" margin={{ top: 'none', bottom: 'xsmall' }}>
              {dayLabel(day)}
            </Heading>

            <Box gap="xsmall" flex={false}>
              {items.map(r => {
                const color = r.category_color || '#E5E7EB'
                const time = r.completed_at_local
                  ? new Date(r.completed_at_local).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
                  : ''
                const points = Number(r.points_awarded ?? r.points ?? 0).toFixed(1)

                return (
                  <Box
                    key={r.id}
                    direction="row"
                    align="center"
                    justify="between"
                    round="small"
                    border={{ color: 'border' }}
                    pad={{ vertical: 'small', horizontal: 'small' }}
                    margin={{ bottom: 'xxsmall' }}
                    flex={false}                             // <-- row itself should not shrink
                    style={{ minHeight: 56, lineHeight: 1.25 }}
                  >
                    {/* LEFT side */}
                    <Box direction="row" align="center" gap="small" flex style={{ minWidth: 0 }}>
                      <Box width="8px" height="8px" round="full" background={color} />
                      {/* green check */}
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                        <circle cx="12" cy="12" r="10" stroke="currentColor" />
                        <path d="M7 12.5l3 3 7-7" stroke="currentColor" strokeWidth="2" fill="none" />
                      </svg>
                      {/* category emoji, fixed size to avoid tall lines */}
                      {r.category_emoji && (
                        <span style={{ fontSize: 18, lineHeight: '18px' }}>{r.category_emoji}</span>
                      )}

                      {/* name + category; minWidth:0 allows truncate */}
                      <Box direction="row" gap="xsmall" align="center" flex style={{ minWidth: 0 }}>
                        <Text weight={600} truncate>{r.name_snapshot}</Text>
                        {r.category_name && (
                          <Text size="small" color="text-weak" truncate>
                            · {r.category_name}
                          </Text>
                        )}
                      </Box>
                    </Box>

                    {/* RIGHT side */}
                    <Box direction="row" align="center" gap="small" flex={false}>
                      <Text size="small" weight={700}>+{points} pts</Text>
                      <Text size="small" color="text-weak">{time}</Text>
                    </Box>
                  </Box>
                )
              })}
            </Box>
          </Box>
        ))}

        <Box height="0" style={{ height: 'calc(140px + env(safe-area-inset-bottom, 0px))' }} />
      </Box>
      <BottomNav />
    </Box>
  )
}
