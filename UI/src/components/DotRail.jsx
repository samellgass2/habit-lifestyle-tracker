// src/components/DotRail.jsx
import { Box } from 'grommet'

export default function DotRail({
  total = 7,
  darkCount = 0,
  orientation = 'vertical',
  topPx = 0,
  inactive = 'rgba(0,0,0,0.25)',
  active = 'text',
}) {
  // Dynamic spacing tuned for 2–3 dots to look best,
  // compresses naturally as total increases.
  const spacingPx = Math.max(2, 12 - total)  // 2..10 px depending on total

  if (orientation === 'horizontal') {
    // Width for each dot after subtracting spacing
    // totalSpacing = (total - 1) * spacingPx
    // dotWidth = (100% - totalSpacing) / total
    const dotWidthCalc = `calc((100% - ${(total - 1) * spacingPx}px) / ${total})`

    return (
      <Box width="100%" flex={false}>
        <Box
          direction="row"
          align="center"
          justify="start"     // LEFT-ALIGNED
          width="70%"         // fixed rail width
          flex={false}
          style={{ gap: `${spacingPx}px` }}  // natural gap spacing
        >
          {Array.from({ length: total }).map((_, i) => {
            const on = i < darkCount
            return (
              <Box
                key={i}
                background={on ? active : inactive}
                style={{
                  width: dotWidthCalc,
                  height: 10,
                  borderRadius: 9999,
                  flex: '0 0 auto',
                }}
              />
            )
          })}
        </Box>
      </Box>
    )
  }

  // Vertical sticky rail (unchanged)
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
            background={on ? active : inactive}
            style={{
              width: 10,
              height: 10,
              borderRadius: 9999,
              flex: '0 0 auto',
            }}
          />
        )
      })}
    </Box>
  )
}
