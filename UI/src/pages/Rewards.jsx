// src/pages/Rewards.jsx
import { useEffect, useState } from 'react'
import { Box, Heading, Text, Button } from 'grommet'
import { SettingsOption, Document } from 'grommet-icons'
import PointsOverTimeChart from '../components/PointsOverTimeChart'
import RewardCard from '../components/RewardCard'
import BottomNav from '../components/BottomNav'
import API from '../api'
import Toast from '../components/Toast'
import { useNavigate } from 'react-router-dom'

export default function Rewards() {
  const nav = useNavigate()
  const [balance, setBalance] = useState(0)
  const [rewards, setRewards] = useState([])
  const [toast, setToast] = useState(null)

  async function load() {
    const { balance, rewards } = await API.getRewards()
    setBalance(balance); setRewards(rewards || [])
  }

  useEffect(() => { load() }, [])

  return (
    <Box fill direction="column">
      <Box
        flex
        overflow="auto"
        style={{ minHeight: 0 }}
        pad={{ horizontal: 'medium', top: 'small' }}
        gap="medium"
      >
        {toast && <Toast message={toast} onClose={() => setToast(null)} />}

        <Box height="30px"/>
        {/* Header */}
        <Box direction="row" justify="between" align="center">
          <Heading level={3} margin="none">Rewards</Heading>
          <Box direction="row" gap="small">
            <Button icon={<Document />} onClick={() => nav('/rewards/history')} plain />
            <Button icon={<SettingsOption />} onClick={() => nav('/rewards/settings')} plain />
          </Box>
        </Box>
        <Text size="small" color="text-weak">Balance: {balance.toFixed(1)} pts</Text>

        {/* Points over time */}
        <PointsOverTimeChart height={220} />

        {/* Rewards list or empty state */}
        {rewards.length === 0 ? (
          <Box
            background="background"
            round="small"
            pad="medium"
            border={{ color: 'border' }}
          >
            <Text>You don’t have any rewards yet.</Text>
            <Button label="Open reward settings" onClick={() => nav('/rewards/settings')} margin={{ top: 'small' }} />
          </Box>
        ) : (
          <Box gap="small">
            {rewards.map(r => (
              <RewardCard
                key={r.id}
                reward={r}
                balance={balance}
                onPurchased={(newBal) => { setBalance(newBal); setToast('Reward purchased! 🎉'); load(); }}
                onError={(msg) => setToast(`Oops… ${msg || 'try again later'}`)}
              />
            ))}
          </Box>
        )}
        <Box height="230px"/>

        {/* spacer so BottomNav never covers the last card */}
        <Box flex={false} height="0" style={{ height: 'calc(140px + env(safe-area-inset-bottom, 0px))' }} />
      </Box>

      <BottomNav />
    </Box>
  )
}
