// src/components/SliderWithTrack.jsx
import { Box, RangeInput } from 'grommet'

export default function SliderWithTrack({ value, min, max, step, onChange, disabled }) {
  return (
    <Box pad={{ vertical: 'small' }} style={{ position: 'relative' }}>
      {/* background track */}
      <Box
        background="light-4"
        height="2px"
        style={{
          position: 'absolute',
          top: '50%',
          left: 0,
          right: 0,
          transform: 'translateY(-50%)',
          pointerEvents: 'none',
          borderRadius: '2px',
        }}
      />
      {/* slider on top */}
      <RangeInput
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={onChange}
        disabled={disabled}
        style={{ position: 'relative', zIndex: 1, width: '100%' }}
      />
    </Box>
  )
}
