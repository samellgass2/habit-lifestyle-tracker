// src/components/EnvBanner.jsx
import { Box, Text } from 'grommet'

export default function EnvBanner() {
  const label = import.meta.env.VITE_ENV_LABEL
  if (!label) return null

  return (
    <Box
      background="status-warning"
      pad={{ horizontal: 'small', vertical: 'xsmall' }}
      align="center"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 1000,
      }}
    >
      <Text size="small" weight="bold" color="black">
        {label} MODE
      </Text>
    </Box>
  )
}
