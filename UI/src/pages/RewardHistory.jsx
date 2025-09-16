// src/pages/RewardHistory.jsx
import { useEffect, useState } from 'react'
import { Box, Heading, Text, Button } from 'grommet'
import API from '../api'
import BottomNav from '../components/BottomNav'
import { FormPreviousLink } from 'grommet-icons'
import { useNavigate } from 'react-router-dom'

export default function RewardHistory() {
const nav = useNavigate()
  const [rows, setRows] = useState([])
  useEffect(() => { API.getRewardPurchases().then(r => setRows(r.purchases || [])) }, [])
  return (
    <Box fill direction="column">
      <Box flex overflow="auto" style={{ minHeight: 0 }} pad={{ horizontal: 'medium', top: 'small' }} gap="medium">
        <Box height="30px"/>
        <Box direction="row" justify="between" align="center">
          <Heading level={3} margin="none">Purchased rewards</Heading>
          <Button icon={<FormPreviousLink />} onClick={() => nav('/rewards')} plain />
        </Box>
        <Box gap="small">
          {rows.map(r => (
            <Box key={r.id} direction="row" justify="between" align="center" pad="small" round="small" border={{ color:'border' }}>
              <Text>{r.emoji || '🎁'} {r.name}</Text>
              <Text size="small" color="text-weak">
                -{r.points_spent.toFixed(1)} pts · {new Date(r.purchased_at_local).toLocaleString()}
              </Text>
            </Box>
          ))}
          {rows.length === 0 && <Text color="text-weak">No purchases yet.</Text>}
        </Box>
        <Box height="0" style={{ height: 'calc(140px + env(safe-area-inset-bottom, 0px))' }} />
      </Box>
      <BottomNav />
    </Box>
  )
}
