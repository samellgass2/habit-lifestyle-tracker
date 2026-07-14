// src/components/BigTextArea.jsx
import { Box, Text } from 'grommet'
import '../styles/bigText.css'

export default function BigTextArea({
  label,
  value,
  onChange,
  placeholder,
  innerRef,
  height = 'clamp(240px, 32vh, 520px)', // BIG by default; tweak per-field if needed
}) {
  return (
    <Box
      ref={innerRef}
      gap="xxsmall"
      pad="medium"
      round="small"
      border={{ color: 'border', size: 'xsmall' }}
      background={{ color: 'background', opacity: 'strong' }}
      margin={{ bottom: 'large' }}
      // make sure parent isn't constraining height
      flex={false}
    >
      <Text size="small" weight={700} color="text-weak">{label}</Text>
      <textarea
        className="big-textarea"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{ height }}   // force the size; ignores any theme rows logic
      />
    </Box>
  )
}
