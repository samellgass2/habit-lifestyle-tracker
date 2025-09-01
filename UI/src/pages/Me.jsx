// src/pages/Me.jsx
import { Box, Button, Heading } from 'grommet'
import { useNavigate } from 'react-router-dom'
import BottomNav from '../components/BottomNav'
import { useLocation } from 'react-router-dom'
import Toast from '../components/Toast'
import { useEffect, useState } from 'react'




export default function Me() {
  const nav = useNavigate()
  const location = useLocation()
  const [toast, setToast] = useState(null)
  useEffect(() => {
    if (location.state?.toast) {
        setToast(location.state.toast)
        nav(location.pathname, { replace: true, state: {} })
    }
    }, [location, nav])

  return (
    <Box fill pad={{ bottom: '64px', horizontal: 'medium', top: 'medium' }} gap="medium">
      <Box height="20px"/>
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
      <Heading level={3} margin="none">Me</Heading>
      <Button label="Update Profile" onClick={() => nav('/me/profile')} />
      <BottomNav />
    </Box>
  )
}
