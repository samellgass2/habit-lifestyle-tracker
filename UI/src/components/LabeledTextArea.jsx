// src/components/LabeledTextArea.jsx
import { Box, Text, TextArea } from 'grommet'

export default function LabeledTextArea({
  label, value, onChange, placeholder, innerRef, height = 'clamp(220px, 32vh, 460px)'
}) {
  return (
    <Box
      ref={innerRef}
      gap="xxsmall"
      pad="medium"
      round="small"
      background={{ color: 'background', opacity: 'strong' }}
      margin={{ bottom: 'large' }}
    >
      <Text size="small" weight={700} color="text-weak">{label}</Text>

      <TextArea
        resize={false}
        value={value}
        placeholder={placeholder}
        onChange={e => onChange(e.target.value)}
        // Inline styles beat theme; this guarantees size on Safari/Chrome/iOS
        style={{
          height,                  // <-- force a big, consistent box
          boxSizing: 'border-box',
          lineHeight: 1.35,
        }}
      />
    </Box>
  )
}
