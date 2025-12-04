import { useMemo, useState } from 'react'
import { Box, Button, Text, Layer } from 'grommet'
import API from '../api'

// helpers: hex → rgb + contrast-aware text color
function hexToRgb(hex) {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex || '')
  if (!m) return { r: 229, g: 231, b: 235 } // #E5E7EB default
  return { r: parseInt(m[1], 16), g: parseInt(m[2], 16), b: parseInt(m[3], 16) }
}
function textOn(hex) {
  const { r, g, b } = hexToRgb(hex)
  // relative luminance
  const srgb = [r, g, b].map(v => {
    const c = v / 255
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
  })
  const L = 0.2126 * srgb[0] + 0.7152 * srgb[1] + 0.0722 * srgb[2]
  return L > 0.6 ? '#111827' /* dark text */ : '#F9FAFB' /* near-white */
}

export default function RewardCard({ reward, balance, onPurchased, onError }) {
  const cost = reward.cost_points
  const progress = Math.min(1, (balance || 0) / (cost || 1))
  const pct = Math.round(progress * 100)
  const ready = progress >= 1 - 1e-9

  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const bg = reward.color || '#E5E7EB'
  const fg = useMemo(() => textOn(bg), [bg])
  const creatorName = reward.creator_username
  const creatorEmoji = reward.creator_emoji
  const creatorColor = reward.creator_color || '#E5E7EB'

  const buy = async () => {
    setBusy(true); setErr(null);
    try {
      const res = await API.purchaseReward(reward.id)
      onPurchased?.(res.balance)
      setConfirm(false)
      // TODO: coin animation
    } catch (e) {
      const msg = e.message || 'Could not complete purchase'
      setErr(msg)
      onError?.(msg)
    } finally { setBusy(false) }
  }

  return (
    <Box
      round="medium"
      pad="medium"
      gap="small"
      // Give the card a colored backdrop and a subtle inner shadow for legibility
      style={{
        background: bg,
        minHeight: 140,
        boxShadow: 'inset 0 0 0 9999px rgba(255,255,255,0.06)',
        // make sure the wrapper doesn't create odd stacking issues
        position: 'relative'
      }}
      border={{ color: 'rgba(0,0,0,0.08)' }}
    >
      {/* header */}
      <Box direction="row" gap="small" align="center" justify="between" flex={false}>
        <Box direction="row" gap="small" align="center" wrap>
          <Text size="large" style={{ color: fg }}>{reward.emoji || '🎁'}</Text>
          <Text size="large" style={{ color: fg }}>{reward.name}</Text>
          {reward.is_recurring ? (
            <Text title="Recurring" style={{ color: fg, opacity: 0.9 }}>♻️</Text>
          ) : null}
        </Box>
        <Text size="small" style={{ color: fg, opacity: 0.85 }}>{cost.toFixed(1)} pts</Text>
      </Box>
      {creatorName && (
        <Box direction="row" gap="xsmall" align="center" margin={{ top: 'xsmall' }}>
          <Box
            width="24px"
            height="24px"
            round="full"
            align="center"
            justify="center"
            background={creatorColor}
            style={{ flexShrink: 0 }}
          >
            <Text size="small" style={{ color: textOn(creatorColor) }}>
              {creatorEmoji || '🙂'}
            </Text>
          </Box>
          <Text size="small" style={{ color: fg, opacity: 0.9 }}>
            from {creatorName}
          </Text>
        </Box>
      )}

      {/* progress */}
      <Box
        round="xsmall"
        height="14px"
        overflow="hidden"
        border={{ color: 'rgba(0,0,0,0.15)' }}
        flex={false}
        style={{ background: 'rgba(255,255,255,0.35)', pointerEvents: 'none' }}
      >
        <Box
          height="100%"
          width={`${pct}%`}
          style={{
            background: ready ? 'rgba(34,197,94,0.9)' : 'rgba(124,58,237,0.9)',
            transition: 'width 200ms ease',
            pointerEvents: 'none'
          }}
        />
      </Box>

      {/* CTA */}
      <Box flex={false}>
        <Button
          primary
          label={ready ? 'Purchase' : 'Not enough points'}
          disabled={!ready || busy}
          onClick={() => {
            console.debug('[RewardCard] open confirm for', reward?.id, reward?.name)
            setConfirm(true)
          }}
          style={{
            color: '#fff',
            background: ready ? 'rgba(34,197,94,0.95)' : 'rgba(124,58,237,0.95)'
          }}
        />
      </Box>

      {/* confirm modal */}
      {confirm && (
        <Layer
          // Layer should float above everything; these props ensure that
          position="center"
          modal
          responsive={false}
          onEsc={() => setConfirm(false)}
          onClickOutside={() => setConfirm(false)}
        >
          <Box pad="medium" gap="small" width="90vw" style={{ maxWidth: 360 }} round="small" background="background">
            <Text weight="bold">Confirm purchase</Text>
            <Text>Spend {cost.toFixed(1)} points on {reward.name}?</Text>
            {err && <Text color="status-critical" size="small">{err}</Text>}
            <Box direction="row" gap="small" margin={{ top: 'small' }}>
              <Button primary label={busy ? 'Purchasing…' : 'Yes'} onClick={buy} disabled={busy} />
              <Button label="Cancel" onClick={() => setConfirm(false)} />
            </Box>
          </Box>
        </Layer>
      )}
    </Box>
  )
}
