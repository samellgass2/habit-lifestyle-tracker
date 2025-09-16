import { Box, Button, TextInput, Text } from 'grommet'
import { Layer } from 'grommet/components/Layer'

const PRESET = [
  '🎁','🍪','🍰','🍣','🍕','🍺','🍷','☕️','🎮','🧩','🧑‍🍳','🎧','📚','🧘','🧑‍🎤','🛍️',
  '🌿','🧼','🛀','🧴','💄','👟','👕','🧥','🎟️','🎬','📷','🚴','🎸','🥾','🏕️','🧳'
]

export default function EmojiPicker({ value, onChange, open, onClose }) {
  if (!open) return null
  return (
    <Layer onEsc={onClose} onClickOutside={onClose} responsive={false} modal position="center">
      <Box pad="medium" gap="small" width="90vw" style={{ maxWidth: 420 }}>
        <Text weight="bold">Choose an emoji</Text>
        <Box direction="row" wrap gap="xsmall">
          {PRESET.map(e => (
            <Button key={e} plain onClick={() => { onChange(e); onClose() }}>
              <Box pad="xsmall" round="xsmall" border>
                <Text style={{ fontSize: 20 }}>{e}</Text>
              </Box>
            </Button>
          ))}
        </Box>
        <Text size="small" color="text-weak">Or paste your own:</Text>
        <TextInput
          value={value || ''}
          onChange={e => onChange(e.target.value)}
          placeholder="e.g. 🎁"
        />
        <Box direction="row" justify="end" margin={{ top: 'small' }}>
          <Button label="Done" onClick={onClose} primary />
        </Box>
      </Box>
    </Layer>
  )
}
