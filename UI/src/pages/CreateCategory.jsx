import { useState } from 'react'
import { Box, Button, Heading, Text, TextInput, RadioButtonGroup } from 'grommet'
import { useNavigate } from 'react-router-dom'
import API from '../api'
import BottomNav from '../components/BottomNav'
import Toast from '../components/Toast'
import { PASTEL_COLORS } from '../lib/profilePresets'
import { AVAILABLE_EMOJIS } from '../components/EmojiPicker.jsx'

export default function CreateCategory() {
  const nav = useNavigate()
  const [name, setName] = useState('')
  const [emoji, setEmoji] = useState('🎯')
  const [color, setColor] = useState(PASTEL_COLORS[0])
  const [mode, setMode]   = useState('tasks') // tasks | time | percent
  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState(null)

  const save = async () => {
    if (!name.trim()) { setToast('Please enter a category name'); return }
    setSaving(true)
    try {
      await API.createCategory({
        category_name: name.trim(),
        emoji, color, points_mode: mode
      })
      nav('/track', { replace: true, state: { toast: 'Category created!' } })
    } catch (e) {
      setToast(e?.message || 'Failed to create category')
    } finally { setSaving(false) }
  }

  return (
    <Box fill pad={{ bottom: '64px', horizontal: 'medium', top: 'medium' }} gap="medium">
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
      <Heading level={3} margin="none">Create Category</Heading>

      <Box gap="small">
        <Text size="small" weight="bold">Name</Text>
        <TextInput value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Fitness" />
      </Box>

      <Box gap="xsmall">
        <Text size="small" weight="bold">Emoji</Text>
        <Box direction="row" wrap gap="small">
          {AVAILABLE_EMOJIS.map(e => (
            <Button key={e} onClick={() => setEmoji(e)} plain hoverIndicator
              style={{
                width: 44, height: 44, borderRadius: 8,
                border: e===emoji ? '2px solid #3b82f6' : '1px solid rgba(0,0,0,0.1)',
                fontSize: 22, display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: '#fff',
              }}
              label={e}
            />
          ))}
        </Box>
      </Box>

      <Box gap="xsmall">
        <Text size="small" weight="bold">Color</Text>
        <Box direction="row" wrap gap="small">
          {PASTEL_COLORS.map(c => (
            <Button key={c} onClick={() => setColor(c)} plain hoverIndicator
              style={{
                width: 36, height: 36, borderRadius: 6, background: c,
                border: c===color ? '2px solid #3b82f6' : '1px solid rgba(0,0,0,0.15)'
              }}
            />
          ))}
        </Box>
      </Box>

      <Box gap="xsmall">
        <Text size="small" weight="bold">Points mode</Text>
        <RadioButtonGroup
          name="mode" direction="row"
          options={[
            { label: 'Tasks', value: 'tasks' },
            { label: 'Time', value: 'time' },
            { label: 'Percent', value: 'percent' },
          ]}
          value={mode}
          onChange={e => setMode(e.target.value)}
        />
      </Box>

      <Box direction="row" gap="small">
        <Button primary label={saving ? 'Saving…' : 'Save'} onClick={save} disabled={saving}/>
        <Button label="Cancel" onClick={() => nav('/track')} />
      </Box>

      <BottomNav />
    </Box>
  )
}
