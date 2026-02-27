// src/components/WeekdayPicker.jsx
import { Box, Button, Text } from 'grommet'
const LABELS = ['Sun','Mon','Tues','Wed','Thurs','Fri','Sat']
const ROWS = [[0,1,2],[3,4,5],[6]]

export default function WeekdayPicker({ value, onChange, stacked=false }) {
  const selected = new Set(value || [])
  const toggle = (idx) => {
    const next = new Set(selected)
    if (next.has(idx)) next.delete(idx)
    else next.add(idx)
    onChange(Array.from(next).sort((a,b)=>a-b))
  }
  return (
    <Box gap="xsmall">
      {(stacked ? ROWS : [LABELS.map((_, i) => i)]).map((row, idx) => (
        <Box key={idx} direction="row" gap="xsmall">
          {row.map(i => (
            <Button
              key={LABELS[i]}
              onClick={() => toggle(i)}
              label={<Text weight={selected.has(i) ? 'bold' : 'normal'}>{LABELS[i]}</Text>}
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
      ))}
    </Box>
  )
}
