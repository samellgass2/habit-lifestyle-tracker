import { Box } from 'grommet'

// Reserves space for the fixed BottomNav (≈72–80px) + iOS safe area.
export default function SafeBottomSpacer({ extra = 100 }) {
  return (
    <Box
      height="0"
      style={{
        // 100px base + any extra you pass + safe-area inset
        height: `calc(${100 + extra}px + env(safe-area-inset-bottom, 0px))`,
      }}
    />
  )
}
