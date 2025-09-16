// src/pages/RewardSettings.jsx
import { useEffect, useState } from 'react'
import { Box, Heading, TextInput, CheckBox, Button, Text, Layer } from 'grommet'
import API from '../api'
import BottomNav from '../components/BottomNav'
import Toast from '../components/Toast'
import { Tip } from 'grommet'
import { Add, Trash, FormPreviousLink } from 'grommet-icons'
import EmojiPicker from '../components/EmojiPicker'
import { useNavigate } from 'react-router-dom'
import ColorPicker from '../components/ColorPicker'

const clampCost = (n) => Math.max(100, Math.min(100000, Number(n || 0)))

function RewardRow({ r, onChange, onDelete, onSave }) {
  const [emojiOpen, setEmojiOpen] = useState(false)
  const [colorOpen, setColorOpen] = useState(false)
  return (
    <Box direction="row" gap="small" align="center" pad="xsmall" border={{ color:'border' }} round="xsmall" wrap>
      <Button onClick={() => setEmojiOpen(true)} plain>
        <Box pad="xsmall" round="xsmall" border><Text style={{ fontSize: 20 }}>{r.emoji || '🎁'}</Text></Box>
      </Button>
      <EmojiPicker value={r.emoji} open={emojiOpen} onChange={e => onChange({ ...r, emoji: e })} onClose={() => setEmojiOpen(false)} />

      <TextInput value={r.name} onChange={e => onChange({ ...r, name: e.target.value })} placeholder="Reward name" />

      <Button plain onClick={() => setColorOpen(true)} title={r.color || '#E5E7EB'}>
       <Box direction="row" gap="xsmall" align="center">
         <Box width="28px" height="20px" round="xsmall" border={{ color:'border' }} style={{ background: r.color || '#E5E7EB' }} />
         <Text size="small" color="text-weak">{r.color || '#E5E7EB'}</Text>
       </Box>
     </Button>
     <ColorPicker
       value={r.color || '#E5E7EB'}
       open={colorOpen}
       onClose={() => setColorOpen(false)}
       onChange={(hex) => onChange({ ...r, color: hex })}
       title="Choose reward color"
     />

      <Tip content="Guidance: ~100 pts ≈ $1">
        <Box direction="row" align="center" gap="xsmall">
          <Text size="small">Cost</Text>
          <TextInput
            value={String(r.cost_points)}
            onChange={e => onChange({ ...r, cost_points: clampCost(e.target.value) })}
            style={{ width: 120 }}
          />
        </Box>
      </Tip>

      <CheckBox label="Recurring" checked={!!r.is_recurring} onChange={e => onChange({ ...r, is_recurring: e.target.checked })} />
      <Button label="Save" onClick={onSave} size="small" />
      <Button icon={<Trash />} onClick={onDelete} plain />
    </Box>
  )
}

export default function RewardSettings() {
  const [rows, setRows] = useState([])
  const [toast, setToast] = useState(null)
  const [showAdd, setShowAdd] = useState(false)
  const [draft, setDraft] = useState({ name:'', emoji:'🎁', color:'#E5E7EB', cost_points:100, is_recurring:false })
  const nav = useNavigate()

  async function load() {
    const { rewards } = await API.getRewards()
    setRows(rewards || [])
  }
  useEffect(() => { load() }, [])

  const saveRow = async (idx) => {
    const r = rows[idx]
    await API.updateReward(r.id, r)
    setToast('Saved!')
  }
  const delRow = async (idx) => {
    const r = rows[idx]
    await API.deleteReward(r.id)
    setRows(prev => prev.filter((_, i) => i !== idx))
    setToast('Deleted')
  }
  const addReward = async () => {
    await API.createReward(draft)
    setShowAdd(false)
    setDraft({ name:'', emoji:'🎁', color:'#E5E7EB', cost_points:100, is_recurring:false })
    await load()
    setToast('Created!')
  }

  return (
    <Box fill direction="column">
      <Box flex overflow="auto" style={{ minHeight: 0 }} pad={{ horizontal: 'medium', top: 'small' }} gap="medium">
        <Box height="30px"/>
        <Box direction="row" justify="between" align="center">
          <Heading level={3} margin="none">Reward settings</Heading>
          <Box direction="row" gap="small">
            <Button icon={<FormPreviousLink />} onClick={() => nav('/rewards')} plain />
            <Button icon={<Add />} primary label="Add" onClick={() => setShowAdd(true)} />
          </Box>
        </Box>
        <Box gap="small">
          {rows.map((r, i) => (
            <RewardRow
              key={r.id}
              r={r}
              onChange={(nr) => setRows(prev => prev.map((x, idx) => idx === i ? nr : x))}
              onDelete={() => delRow(i)}
              onSave={() => saveRow(i)}
            />
          ))}
        </Box>

        <Box height="0" style={{ height: 'calc(140px + env(safe-area-inset-bottom, 0px))' }} />

        {/* "Add" modal: clamp + emoji picker too */}
        {showAdd && (
          <Layer position="center" modal responsive={false} onEsc={() => setShowAdd(false)} onClickOutside={() => setShowAdd(false)}>
            <Box pad="medium" gap="small" width="90vw" style={{ maxWidth: 420 }} round="small" background="background">
              <Heading level={4} margin="none">New reward</Heading>

              <Box direction="row" gap="small" align="center">
                <Button onClick={() => setDraft(d => ({ ...d, open:true }))} plain>
                  <Box pad="xsmall" round="xsmall" border><Text style={{ fontSize: 20 }}>{draft.emoji || '🎁'}</Text></Box>
                </Button>
                <EmojiPicker value={draft.emoji} open={!!draft.open} onChange={e => setDraft(d => ({ ...d, emoji:e }))} onClose={() => setDraft(d => ({ ...d, open:false }))} />
                <TextInput placeholder="Name" value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} />
              </Box>

              <Button plain onClick={() => setDraft(d => ({ ...d, colorOpen: true }))}>
   <Box direction="row" gap="xsmall" align="center">
     <Box width="28px" height="20px" round="xsmall" border={{ color:'border' }} style={{ background: draft.color || '#E5E7EB' }} />
     <Text size="small" color="text-weak">{draft.color || '#E5E7EB'}</Text>
   </Box>
    </Button>
        <ColorPicker
        value={draft.color || '#E5E7EB'}
        open={!!draft.colorOpen}
        onClose={() => setDraft(d => ({ ...d, colorOpen: false }))}
        onChange={(hex) => setDraft(d => ({ ...d, color: hex }))}
        title="Choose reward color"
        />
        <Text>How many points is it worth? ($1 ~= 100points)</Text>
                <TextInput
                    placeholder="Cost points (100)"
                    type="number"
                    value={draft.cost_points}
                    onChange={e =>
                    setDraft({ ...draft, cost_points: e.target.value }) // keep raw string while typing
                    }
                    onBlur={() => {
                    const n = Number(draft.cost_points)
                    if (!isNaN(n)) {
                        setDraft({
                        ...draft,
                        cost_points: Math.max(100, Math.min(100000, n)), // clamp to range
                        })
                    }
                    }}
                />
              <CheckBox label="Recurring" checked={draft.is_recurring} onChange={e => setDraft({ ...draft, is_recurring: e.target.checked })} />

              <Box direction="row" gap="small" margin={{ top: 'small' }}>
                <Button primary label="Create" onClick={addReward} />
                <Button label="Cancel" onClick={() => setShowAdd(false)} />
              </Box>
            </Box>
          </Layer>
        )}
      </Box>
      <BottomNav />
    </Box>
  )
}
