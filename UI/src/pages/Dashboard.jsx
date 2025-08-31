// src/pages/Dashboard.jsx
import { Box, Heading, Text } from 'grommet'
import BottomNav from '../components/BottomNav'
import { useAuth } from '../auth.jsx'
import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import Toast from '../components/Toast'


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
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}

      <Heading level={3} margin={{ bottom: 'small' }}>Dashboard</Heading>
      <Text>Welcome, {user?.username}</Text>
      {/* your charts/cards here */}
      <BottomNav />
    </Box>
  )
}
