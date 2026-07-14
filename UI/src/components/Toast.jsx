// src/components/Toast.jsx
import { Layer, Box, Text } from 'grommet'
import { useEffect } from 'react'

export default function Toast({
  message,
  onClose,
  duration = 2500,
  background = 'brand',  // Grommet "brand" is usually blue, override if needed
}) {
  useEffect(() => {
    const t = setTimeout(onClose, duration)
    return () => clearTimeout(t)
  }, [onClose, duration])

  return (
    <Layer
      position="top"
      modal={false}
      onEsc={onClose}
      responsive={false}
      plain
      margin={{ top: 'large' }}   // <-- adds ~48px offset from the very top
    >
      <Box
        background={background}
        round="medium"
        pad={{ horizontal: 'large', vertical: 'small' }}
        align="center"
        animation="fadeIn"
        style={{
          minWidth: '320px',
          maxWidth: '600px',
          margin: '0 auto',       // center horizontally
          boxShadow: '0 2px 6px rgba(0,0,0,0.25)',
        }}
      >
        <Text color="white" weight={600}>{message}</Text>
      </Box>
    </Layer>
  )
}
