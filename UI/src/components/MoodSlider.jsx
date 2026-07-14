// src/components/MoodSlider.jsx
import { Box, RangeInput, Text } from 'grommet'
import '../styles/mood.css'

export default function MoodSlider({ value, onChange }) {
  return (
    <Box
      pad="medium"
      margin={{ bottom: 'large' }}
      round="small"
      border={{ color: 'border', size: 'xsmall' }}
      background={{ color: 'background', opacity: 'strong' }}
      gap="small"
      // ensure it doesn't get covered/overlapped by neighbors
      style={{
        minHeight: 160,
        position: 'relative',
        overflow: 'visible',
        zIndex: 0,
        paddingBottom: 24,              // extra room for the thumb drop
      }}
    >
      <Text size="small" weight={700} color="text-weak">Mood right now</Text>

      <Box direction="row" justify="between" align="center" margin={{ bottom: 'xsmall' }}>
        <Text aria-hidden style={{ lineHeight: 1.2 }}>:(</Text>
        <Text>2</Text><Text>3</Text><Text>4</Text>
        <Text aria-hidden style={{ lineHeight: 1.2 }}>:D</Text>
      </Box>

      <RangeInput
        className="mood"
        min={1} max={5} step={1}
        value={value}
        onChange={e => onChange(parseInt(e.target.value, 10))}
        style={{ width: '100%', display: 'block' }}
      />
    </Box>
  )
}
