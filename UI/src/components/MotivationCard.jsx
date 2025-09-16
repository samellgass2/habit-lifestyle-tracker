import { useEffect, useState } from 'react'
import { Box, Button, Text } from 'grommet'
import API from '../api'
import { browserTimeZone } from '../lib/tz'

// simple relative-time formatter (minutes/hours/days)
function formatRelative(isoUtc) {
  if (!isoUtc) return ''
  const then = new Date(isoUtc)                // server returns UTC ISO
  const now = new Date()
  const diffMs = now - then
  const s = Math.max(0, Math.floor(diffMs / 1000))
  if (s < 60) return 'just now'
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} min ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} hr${h === 1 ? '' : 's'} ago`
  const d = Math.floor(h / 24)
  return `${d} day${d === 1 ? '' : 's'} ago`
}

function toLocalString(isoUtc) {
  if (!isoUtc) return ''
  try {
    const tz = browserTimeZone()
    return new Date(isoUtc).toLocaleString([], { timeZone: tz })
  } catch {
    return new Date(isoUtc).toLocaleString()
  }
}

export default function MotivationCard({ onToast }) {
  const [loading, setLoading] = useState(true)
  const [text, setText] = useState('')
  const [generatedAt, setGeneratedAt] = useState(null)

  async function load() {
    setLoading(true)
    try {
      const res = await API.getMotivation()
      if (res.available) {
        setText(res.text || '')
        setGeneratedAt(res.generated_at || null)
      } else {
        setText('') ; setGeneratedAt(null)
      }
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  async function refresh() {
    try {
      const res = await API.refreshMotivation()
      setText(res.text || '')
      setGeneratedAt(res.generated_at || null)
      onToast?.('New motivation ✨')
    } catch (e) {
        if (e.toString().split('Error: ').length > 1) {
            onToast?.(e.toString().split('Error: ')[1].toString())
        } else {
            onToast?.('Try again soon')
        }
    }
  }

  return (
    <Box
      round="small"
      pad="small"
      background="background"
      gap="xsmall"
    >
      <Box direction="row" justify="between" align="center">
        <Text weight="bold">Daily Motivation</Text>
        <Button size="small" label="Refresh" onClick={refresh} />
      </Box>

      {loading ? (
        <Text size="small" color="text-weak">Loading…</Text>
      ) : text ? (
        <>
          <Text style={{ fontStyle: 'italic' }}>{text}</Text>
          {generatedAt && (
            <Text size="xsmall" color="text-weak" margin={{ top: 'xxsmall' }}>
              updated {formatRelative(generatedAt)} • {toLocalString(generatedAt)}
            </Text>
          )}
        </>
      ) : (
        <Text size="small" color="text-weak">
          No motivation yet — press Refresh to generate one.
        </Text>
      )}
    </Box>
  )
}
