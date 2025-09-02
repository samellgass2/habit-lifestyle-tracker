import { Box, Card, CardBody, Heading, Text } from 'grommet'
import { Edit, Clipboard } from 'grommet-icons'
import BottomNav from '../components/BottomNav'
import { useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import API from '../api'
import { localISODate } from '../lib/date'

export default function Intake() {
  const nav = useNavigate()
  const [hasToday, setHasToday] = useState(false)
  const [todayLog, setTodayLog] = useState(null)
  useEffect(() => {
    (async () => {
      try {
        const day = localISODate()
        const res = await API.getDayLog(day)
        if (res?.found) {
          setHasToday(true)
          setTodayLog(res.reflection)
        } else {
          setHasToday(false)
          setTodayLog(null)
        }
      } catch {
        setHasToday(false)
        setTodayLog(null)
      }
    })()
  }, [])


  const Tile = ({ icon:Icon, title, subtitle, to, state }) => (
    <Card onClick={() => nav(to, { state })} pad="large" height="25vh" hoverIndicator focusIndicator={false}>
      <CardBody direction="row" gap="medium" align="center" justify="center" fill>
        <Icon size="xlarge" />
        <Box>
          <Heading level={2} margin="none">{title}</Heading>
          <Text size="medium" color="text-weak">{subtitle}</Text>
        </Box>
      </CardBody>
    </Card>
  )

  return (
    <Box fill pad={{ top: 'medium', bottom: '72px', horizontal: 'medium' }} gap="medium">
      <Tile
        icon={Edit}
        title={hasToday ? 'UPDATE DAY LOG' : 'DAY LOG'}
        subtitle={hasToday ? 'Continue today’s reflection' : 'Journal + mood + gratitude'}
        to="/intake/daily"
        state={{ initial: todayLog, day: localISODate() }}
      />
      <BottomNav />
    </Box>
  )
}
