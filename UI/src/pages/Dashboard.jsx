// src/pages/Dashboard.jsx
import { Box, Heading, Text } from 'grommet'
import BottomNav from '../components/BottomNav'
import { useAuth } from '../auth.jsx'
import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import CalendarWidget from '../components/CalendarWidget'
import Toast from '../components/Toast'
import InsightsCard from '../components/InsightsCard'


export default function Dashboard() {
  // Handle receiving state 
  const location = useLocation()
  const nav = useNavigate()
  const [toast, setToast] = useState(null)

  // Handle toast popups on redirect
  useEffect(() => {
    if (location.state?.toast) {
      setToast(location.state.toast)
      // clear state so if user refreshes, toast doesn't reappear
      nav(location.pathname, { replace: true, state: {} })
    }
  }, [location, nav])

  const { user } = useAuth()
  return (
    <Box fill pad={{ bottom: '64px', horizontal: 'medium', top: 'medium' }}>
      {/* NOTIFICATIONS + SETTINGS */}
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}

      {/* DASHBOARD CONTENT */}

      <Heading level={1} margin={{ bottom: 'small' }}>{user?.username + "'s Dashboard " + (user?.emoji || '🙂')}</Heading>

      {/* your charts/cards here */}
      <CalendarWidget />
      <Box height="60px"/>
      <InsightsCard />

      {/* FOOTER */}
      <BottomNav />
    </Box>
  )
}
