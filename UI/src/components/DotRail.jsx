// src/components/DotRail.jsx
import { Box } from 'grommet'

export default function DotRail({
  total = 7,
  darkCount = 0,
  topPx = 0,
  inactive = 'rgba(0,0,0,0.25)',  // darker light dots
// theme token for a darker light gray
  active = 'text',            // theme token for active
}) {
  return (
    <Box
      align="center"
      pad={{ vertical: 'small' }}
      width="8%"
      minWidth="28px"
      style={{
        position: 'sticky',
        top: `${topPx}px`,
        height: `calc(100vh - ${topPx}px)`,
        alignSelf: 'start',
      }}
    >
      {Array.from({ length: total }).map((_, i) => {
        const on = i < darkCount
        return (
          <Box
            key={i}
            margin={{ vertical: '8px' }}
            // Force perfect circles; never let flex stretch these
            style={{
              width: 10,
              height: 10,
              aspectRatio: '1 / 1',
              borderRadius: 9999,
              flex: '0 0 auto',
            }}
            background={on ? active : inactive}
          />
        )
      })}
    </Box>
  )
}
