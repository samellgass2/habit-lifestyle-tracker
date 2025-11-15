// src/pages/Dashboard.jsx
import { Box, Heading, Text, Button } from 'grommet'
import { MailOption } from 'grommet-icons'
import BottomNav from '../components/BottomNav'
import { useAuth } from '../auth.jsx'
import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import CalendarWidget from '../components/CalendarWidget'
import Toast from '../components/Toast'
import InsightsCard from '../components/InsightsCard'
import API from '../api'
import PointsByCategoryChart from '../components/PointsByCategoryChart.jsx'
import PointsOverTimeChart from '../components/PointsOverTimeChart.jsx'
import GratitudeCloud from '../components/GratitudeCloud'
import MotivationCard from '../components/MotivationCard'
import FocusCard from '../components/FocusCard.jsx'
import FriendFeed from '../components/FriendFeed'



export default function Dashboard() {
  const location = useLocation()
  const nav = useNavigate()
  const [toast, setToast] = useState(null)
  const [points, setPoints] = useState(0.0)
  const [hasNotifications, setHasNotifications] = useState(false)
  const { user } = useAuth()

  useEffect(() => {
    if (location.state?.toast) {
      setToast(location.state.toast)
      nav(location.pathname, { replace: true, state: {} })
    }
  }, [location, nav])

  useEffect(() => {
    (async () => {
      const res = await API.getPoints()
      setPoints(res)
      const data = await API.getInbox()
      setHasNotifications(data?.comments?.length > 0 || data?.reactions?.length > 0 || data?.friend_requests.length > 0)
    })()
  }, [])

  const inboxLabel = hasNotifications ? '(!)' : ''


  return (
    // Root flex column
    <Box fill direction="column">
      {/* SCROLLING CONTENT (the ONLY flex child) */}
      <Box
        flex="grow"                 // this grows to fill
        overflow="auto"             // make this the scroller
        style={{ minHeight: 0 }}    // <-- CRITICAL: allow it to shrink instead of squish siblings
        pad={{ horizontal: 'medium', top: 'small' }}
        gap="medium"
      >
        {toast && <Toast message={toast} onClose={() => setToast(null)} />}

        <Box>
          <Heading level={3} margin={{ bottom: 'xxsmall' }}>
            {user?.username}'s Dashboard {user?.emoji || '🙂'}
          </Heading>
          <Text size="medium" color="text-weak">
            Balance: {(points?.balance || 0).toFixed(1)} pts
          </Text>

          <Button
          icon={<MailOption />}
          label={inboxLabel}
          onClick={() => nav('/inbox')}
        />
        </Box>

        
        

        {/* Gratitude Cloud & Motivation*/}
        <Heading level={2} margin="none">
          {'Daily Reminders :)'}
        </Heading>
        <Heading level={4} margin="none">
          {"What you're grateful for <3"}
        </Heading>
        <GratitudeCloud height={160}/>
        <MotivationCard onToast={setToast} />

        {/* Weekly focus / happenings */}
        <FocusCard api={API} />

        
        {/* Charts (do NOT give these flex) */}
        <Heading level={2}>
          {'Habit Tracking'}
        </Heading>
        <PointsOverTimeChart height={120} />
        <PointsByCategoryChart height={140} />

        {/* Reflections section */}
        <Box gap="small">
          <Heading level={4} margin="none">Reflections</Heading>

          <Box
            background="background"
            round="small"
            pad="small"
            border={{ color: 'border', size: 'xsmall' }}
          >
            <CalendarWidget />
          </Box>

          <Box
            background="background"
            round="small"
            pad="small"
            border={{ color: 'border', size: 'xsmall' }}
            style={{ minHeight: 250 }}
          >
            <InsightsCard />
          </Box>
        </Box>

        {/* Spacer INSIDE the scroller; must not flex */}
        <Box
          flex={false}
          height="0"
          style={{ height: 'calc(140px + env(safe-area-inset-bottom, 0px))' }}
        />
      </Box>

      {/* Fixed bottom nav as sibling, NOT inside the scroller */}
      <BottomNav />
    </Box>
  )
}
