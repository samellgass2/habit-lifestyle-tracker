import { useEffect, useState } from 'react'
import { Box, Text, Button } from 'grommet'

export default function FocusCard({ api }) {
  const [data, setData] = useState(null)
  useEffect(() => { api.getFocus().then(setData).catch(() => setData(null)) }, [])

  if (!data?.available) return null
  const { category, blurb, multiplier } = data
  return (
    <Box pad="medium" round="medium" gap="small"
         background={category.color || 'background-back'}
         style={{ boxShadow: 'inset 0 0 0 9999px rgba(255,255,255,0.06)' }}>
      <Text size="large">🔥 In Focus: {category.emoji} {category.name}</Text>
      {blurb && <Text color="text-weak">{blurb}</Text>}
      <Text weight="bold" margin={{ top: 'xsmall' }}>
        All '{category.name}' habits are worth {multiplier}× this week!
      </Text>
    </Box>
  )
}
