// src/pages/Dashboard.jsx
import { Box, Heading, Text } from 'grommet'
import BottomNav from '../components/BottomNav'
import { useAuth } from '../auth.jsx'
import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import CalendarWidget from '../components/CalendarWidget'
import Toast from '../components/Toast'
import InsightsCard from '../components/InsightsCard'
import API from '../api'



export default function Dashboard() {
  // Handle receiving state 
  const location = useLocation()
  const nav = useNavigate()
  const [toast, setToast] = useState(null)
  const [points, setPoints] = useState(0.0)

  // Handle toast popups on redirect
  useEffect(() => {
    if (location.state?.toast) {
      setToast(location.state.toast)
      // clear state so if user refreshes, toast doesn't reappear
      nav(location.pathname, { replace: true, state: {} })
    }
  }, [location, nav])

  useEffect(() => {
    (async () => {
      const res = await API.getPoints()
      setPoints(res)
    })()
  }, [])

  const { user } = useAuth()
  return (
    <Box fill pad={{ bottom: '64px', horizontal: 'medium', top: 'medium' }}>
      {/* NOTIFICATIONS + SETTINGS */}
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}

      {/* DASHBOARD CONTENT */}

      <Heading level={1} margin={{ bottom: 'small' }}>{user?.username + "'s Dashboard " + (user?.emoji || '🙂')}</Heading>

      <h2>Points: {points?.balance || 0.0}</h2>

      {/* your charts/cards here */}
      <h2>Reflections</h2>
      <CalendarWidget />
      <Box height="60px"/>
      <InsightsCard />

      <h2>What You're Grateful For (WIP)</h2>

      {/* FOOTER */}
      <BottomNav />
    </Box>
  )
}
