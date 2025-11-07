// src/components/WeekdayPicker.jsx
import { Box, Button, Text } from 'grommet'
const LABELS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']

export default function WeekdayPicker({ value, onChange }) {
  const selected = new Set(value || [])
  const toggle = (idx) => {
    const next = new Set(selected)
    if (next.has(idx)) next.delete(idx)
    else next.add(idx)
    onChange(Array.from(next).sort((a,b)=>a-b))
  }
  return (
    <Box direction="row" gap="xsmall">
      {LABELS.map((lab, i) => (
        <Button
          key={lab}
          onClick={() => toggle(i)}
          label={<Text weight={selected.has(i) ? 'bold' : 'normal'}>{lab}</Text>}
          plain
          style={{
            border: '1px solid var(--border, #ddd)',
            borderRadius: 8,
            padding: '6px 10px',
            background: selected.has(i) ? 'var(--accent, #eee)' : 'transparent'
          }}
        />
      ))}
    </Box>
  )
}
