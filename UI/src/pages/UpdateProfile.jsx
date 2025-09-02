// src/pages/UpdateProfile.jsx
import { useEffect, useState } from 'react'
import { Box, Button, Heading, Text } from 'grommet'
import API from '../api'
import { useNavigate } from 'react-router-dom'
import { PASTEL_COLORS, EMOJI_CHOICES } from '../lib/profilePresets'
import BottomNav from '../components/BottomNav'
import Toast from '../components/Toast'
import { useAuth } from '../auth.jsx'



export default function UpdateProfile() {
  const nav = useNavigate()
  const [loading, setLoading] = useState(true)
  const [emoji, setEmoji] = useState('')
  const [color, setColor] = useState('')
  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState(null)

  const { refreshAuth } = useAuth()

  useEffect(() => {
    (async () => {
      try {
        const p = await API.getMyProfile()
        setEmoji(p.emoji || '')
        setColor(p.accent_color || '')
      } finally { setLoading(false) }
    })()
  }, [])

  const save = async () => {
    setSaving(true)
    try {
      const updated = await API.updateMyProfile({ emoji, accent_color: color })
      // Update local state immediately
      await refreshAuth()

      // success → go back to Me with toast
      nav('/account', { replace: true, state: { toast: 'Profile updated!' } })
    } catch (e) {
      // show server message if present
      const msg = e?.message || e?.error || 'Oops! Could not update profile.'
      setToast(msg)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return null

  return (
    <Box fill pad={{ bottom: '64px', horizontal: 'medium', top: 'medium' }} gap="medium">
      <Box height="20px"/>
      <Heading level={3} margin="none">Update Profile</Heading>
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}

      {/* Preview */}
      <Box direction="row" gap="small" align="center">
        <Box
          width="48px" height="48px" round="xsmall"
          align="center" justify="center"
          style={{ background: color || '#E5E7EB', fontSize: 24 }}
        >
          <span>{emoji || '🙂'}</span>
        </Box>
        <Text color="text-weak">This is how your Me icon will look.</Text>
      </Box>

      {/* Emoji selector */}
      <Box gap="xsmall">
        <Text size="small" weight={700} color="text-weak">Choose an emoji</Text>
        <Box direction="row" wrap gap="small">
          {EMOJI_CHOICES.map(e => (
            <Button
              key={e}
              onClick={() => setEmoji(e)}
              plain
              hoverIndicator
              style={{
                width: 44, height: 44, borderRadius: 8,
                border: e===emoji ? '2px solid #3b82f6' : '1px solid rgba(0,0,0,0.1)',
                fontSize: 22,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: '#fff',
              }}
              label={e}
            />
          ))}
        </Box>
      </Box>

      {/* Color selector */}
      <Box gap="xsmall">
        <Text size="small" weight={700} color="text-weak">Choose a background color</Text>
        <Box direction="row" wrap gap="small">
          {PASTEL_COLORS.map(c => (
            <Button
              key={c}
              onClick={() => setColor(c)}
              plain
              hoverIndicator
              style={{
                width: 36, height: 36, borderRadius: 6, background: c,
                border: c===color ? '2px solid #3b82f6' : '1px solid rgba(0,0,0,0.15)'
              }}
            />
          ))}
        </Box>
      </Box>

      <Box direction="row" gap="small" margin={{ top: 'small' }}>
        <Button label={saving ? 'Saving…' : 'Save'} primary onClick={save} disabled={saving} />
        <Button label="Cancel" onClick={() => nav('/account')} />
      </Box>

      <BottomNav />
    </Box>
  )
}
