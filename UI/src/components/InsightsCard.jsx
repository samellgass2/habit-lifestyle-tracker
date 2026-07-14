// src/components/InsightsCard.jsx
import { useEffect, useState } from 'react'
import { Box, Button, Heading, Text } from 'grommet'
import API from '../api'
import { useNavigate } from 'react-router-dom'

const scopes = [
  { key: 'day',   label: 'Yesterday' },
  { key: 'week',  label: 'Week' },
  { key: 'month', label: 'Month' },
]

export default function InsightsCard() {
  const [scope, setScope] = useState('day')
  const [data, setData]   = useState(null)
  const [loading, setLoading] = useState(false)
  const nav = useNavigate()

  useEffect(() => {
    let alive = true
    setLoading(true)
    API.getAISummary(scope).then(res => { if (alive) setData(res) })
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [scope])

  const heading = data?.label || scopes.find(s => s.key === scope)?.label

  return (
    <Box pad="medium" round="small" border={{ color:'border', size:'xsmall' }} background="background" gap="small">
      {/* Header + scope buttons */}
      <Box direction="row" align="center" justify="between">
        <Heading level={4} margin="none">Your {heading}</Heading>
        <Box direction="row" gap="xsmall">
          {scopes.map(s => (
            <Button
              key={s.key}
              size="small"
              label={s.key === 'day' ? 'Day' : s.key === 'week' ? 'Week' : 'Month'}
              onClick={() => setScope(s.key)}
              primary={scope === s.key}
            />
          ))}
        </Box>
      </Box>

      {/* Body */}
      {loading && <Text size="small" color="text-weak">Loading…</Text>}

      {!loading && data?.available && (
        <Box>
          <Text size="small" color="text-weak" weight={700} margin={{ bottom: 'xxsmall' }}>Summary:</Text>
          <Text>{data.summary}</Text>
        </Box>
      )}

      {!loading && !data?.available && (
        <Box gap="xsmall">
          <Text>{data?.message || 'No summary yet.'}</Text>
          {/* Only show CTA when we’re on Yesterday scope or message hints about today */}
          {scope === 'day' && (
            <Button
              label="Open Day Log"
              onClick={() => nav('/reflect/daily')}
            />
          )}
        </Box>
      )}
    </Box>
  )
}
