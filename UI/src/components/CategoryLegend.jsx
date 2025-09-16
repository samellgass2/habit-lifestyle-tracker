import { Box, Text } from 'grommet'

export default function CategoryLegend({ catMeta, focusedId, onToggle }) {
  const cats = Object.values(catMeta)
  return (
    <Box direction="row" wrap gap="small" margin={{ top: 'small' }}>
      {cats.map(c => {
        const active = !focusedId || focusedId === c.id
        return (
          <Box
            key={c.id}
            direction="row"
            gap="xsmall"
            align="center"
            pad="xsmall"
            round="xsmall"
            border={{ color: active ? 'border' : 'background-contrast' }}
            onClick={() => onToggle(focusedId === c.id ? null : c.id)}
            style={{ cursor: 'pointer', opacity: active ? 1 : 0.35 }}
          >
            <span
              style={{
                display: 'inline-block',
                width: 12, height: 12, borderRadius: 3,
                background: c.color || '#999'
              }}
            />
            <Text size="small">{c.emoji || '📁'} {c.name}</Text>
          </Box>
        )
      })}
    </Box>
  )
}
