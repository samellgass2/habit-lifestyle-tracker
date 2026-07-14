import { useMemo, useState } from 'react'
import { Box, Button, Text, TextInput } from 'grommet'
import { Layer } from 'grommet/components/Layer'

// pleasant pastel-ish presets (feel free to tweak)
export const PRESET_REWARD_COLORS = [
  '#FDE68A', '#FCA5A5', '#FBCFE8', '#A7F3D0',
  '#BFDBFE', '#DDD6FE', '#FEE2E2', '#FFE4E6',
  '#E5E7EB', '#D1FAE5', '#C7D2FE', '#FDE2FF',
  '#F5F5F4', '#FECACA', '#E9D5FF', '#E2E8F0'
]

// simple hex validator: #RGB or #RRGGBB (case-insensitive)
const HEX_OK = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i

export default function ColorPicker({
  value,
  onChange,
  open,
  onClose,
  presets = PRESET_REWARD_COLORS,
  title = 'Choose a color'
}) {
  const [draft, setDraft] = useState(value || '#E5E7EB')
  const valid = useMemo(() => HEX_OK.test(draft || ''), [draft])

  if (!open) return null

  const select = (hex) => { onChange(hex); onClose?.() }

  return (
    <Layer onEsc={onClose} onClickOutside={onClose} modal position="center" responsive={false}>
      <Box pad="medium" gap="small" width="90vw" style={{ maxWidth: 420 }} round="small" background="background">
        <Text weight="bold">{title}</Text>

        {/* presets */}
        <Box direction="row" wrap gap="xsmall">
          {presets.map((hex) => (
            <Button key={hex} plain onClick={() => select(hex)}>
              <Box
                width="36px"
                height="28px"
                round="xsmall"
                border={{ color: 'border' }}
                style={{ background: hex }}
              />
            </Button>
          ))}
        </Box>

        {/* custom hex */}
        <Text size="small" color="text-weak">Or enter a HEX color:</Text>
        <Box direction="row" gap="small" align="center">
          <TextInput
            value={draft}
            onChange={e => setDraft(e.target.value)}
            placeholder="#AABBCC"
            style={{ width: 140 }}
          />
          <Box
            width="36px"
            height="28px"
            round="xsmall"
            border={{ color: valid ? 'border' : 'status-critical' }}
            style={{ background: valid ? draft : 'transparent' }}
            title={valid ? draft : 'Invalid hex'}
          />
          <Button
            label="Use"
            primary
            onClick={() => valid && select(draft)}
            disabled={!valid}
          />
        </Box>

        <Box direction="row" justify="end" margin={{ top: 'small' }}>
          <Button label="Done" onClick={onClose} />
        </Box>
      </Box>
    </Layer>
  )
}
