// src/pages/TrackCreateAI.jsx
import { useEffect, useState } from 'react'
import { Box, Button, Heading, Select, Text, TextInput, Spinner, Card, CardBody } from 'grommet'
import { FormPreviousLink, Magic } from 'grommet-icons'
import { useNavigate } from 'react-router-dom'
import BottomNav from '../components/BottomNav'
import API from '../api'
import Toast from '../components/Toast'
import HabitCard from '../components/HabitCard'
import { potentialPointsForHabit } from '../lib/points'

export default function TrackCreateAI() {
  const nav = useNavigate()
  const [cats, setCats] = useState([])
  const [catId, setCatId] = useState(null)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [proposal, setProposal] = useState(null)
  const [toast, setToast] = useState(null)

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const r = await API.listCategories()
        if (!alive) return
        const items = r.categories || r.items || r || []
        setCats(items)
      } catch (e) {
        if (alive) setCats([])
      }
    })()
    return () => { alive = false }
  }, [])

  const catOptions = cats.map(c => ({ value: c.id, label: `${c.emoji || ''} ${c.category_name}`.trim() }))

  async function onGenerate() {
    setLoading(true)
    setError(null)
    setProposal(null)
    try {
      const body = {
        ...(catId ? { category_id: catId } : {}),
        ...(input ? { user_input: input } : {}),
      }
      const r = await API.generateHabitPreview(body)
      setProposal(r.proposal)
    } catch (e) {
      // bubble 429 messaging if present
      setError(e?.data?.error || e.message || 'Failed to generate')
    } finally {
      setLoading(false)
    }
  }

  async function onConfirmSave() {
    if (!proposal) return
    try {
      // You decide shape of proposal. Minimal pass-through plus ai_created flag:
      const res = await API.createHabit(
        { ...proposal, 
            category_id: catId ?? proposal.category_id,
            ai_created: true })
      
      // after saving, bounce back to track
      nav('/track', { replace: true, state: { toast: 'Habit saved 🎉' }})
    } catch (e) {
      setError(e?.data?.error || e.message || 'Failed to save habit')
    }
  }

  // helper to map proposal + selected category to HabitCard shape
    function buildPreviewHabit(proposal, cats, selectedCatId) {
    const cat = cats.find(c => c.id === selectedCatId) || {}
    // Default to 'tasks' if unknown
    const points_mode = cat.points_mode || 'tasks'

    const potential = potentialPointsForHabit(
        points_mode,
        proposal.base_value ?? 1,
        proposal.challenge ?? 'easy',
        proposal.importance ?? 1,
        {
            time_target: proposal.time_minutes ?? null,     // proposal target for time categories
            percent_target: proposal.percent_target ?? null // proposal target for percent categories
        }
    )

    return {
        id: 0, // no real id yet
        name: proposal.name || 'New Habit',
        type: proposal.type || 'recurring',
        date_local: proposal.date_local || null,

        // category visual bits the card expects
        category: {
        id: cat.id,
        emoji: cat.emoji || '✅',
        color: cat.color || '#E5E7EB',
        category_name: cat.category_name || 'Uncategorized',
        points_mode,
        },

        // scoring knobs the card uses
        points_mode,
        base_value: proposal.base_value ?? 1,
        potential_points: potential,
        time_minutes: proposal.time_minutes || null,
        percent_target: proposal.percent_target || null,

        // disable the CTA for preview
        completed_today: true,
    }
    }

  return (
    <Box fill>
        {toast && <Toast message={toast} onClose={() => setToast(null)} />}
      <Box pad={{ horizontal: 'medium', top: 'small' }} gap="medium">
        <Box height="30px" />
        <Box direction="row" justify="between" align="center">
          <Heading level={3} margin="none">AI Habits</Heading>
          <Button icon={<FormPreviousLink size="large" />} onClick={() => nav('/track/create')} plain pad="xsmall" />
        </Box>

        {!proposal && (
          <Box gap="small">
            <Text color="text-weak">
              What do you want to focus on? A weakness? A strength? A new hobby?
            </Text>

            <Box gap="xsmall">
              <Text size="small">Category (optional)</Text>
              <Select
                placeholder="Pick a category…"
                options={catOptions}
                labelKey="label"
                valueKey={{ key: 'value', reduce: true }}
                value={catId}
                onChange={({ option }) => setCatId(option?.value ?? null)}
              />
            </Box>

            <Box gap="xsmall">
              <Text size="small">Your focus (optional)</Text>
              <TextInput
                placeholder="e.g., Improve guitar sight-reading, or 10k steps on weekdays…"
                value={input}
                onChange={e => setInput(e.target.value)}
                maxLength={280}
              />
              <Text size="xsmall" color="text-weak">{(input?.length||0)}/280</Text>
            </Box>

            <Box direction="row" gap="small" margin={{ top: 'small' }}>
              <Button
                primary
                icon={<Magic />}
                label={loading ? 'Generating…' : 'Generate'}
                onClick={onGenerate}
                disabled={loading}
              />
              {loading && <Spinner />}
            </Box>

            {error && <Text color="status-critical">{error}</Text>}
          </Box>
        )}

        {proposal && (
            <Box gap="medium">

                <Text
                        size="medium"
                        color="text-weak"
                        margin={{ top: 'small' }}
                        style={{ fontStyle: 'italic', lineHeight: 1.4 }}
                    >
                        {'AI Habit preview:'}
                    </Text>

                {/* Preview as an actual HabitCard (CTA disabled by completed_today=true) */}
                <HabitCard
                habit={buildPreviewHabit(proposal, cats, catId)}
                // no onCompleted/onDeleted: it’s a preview
                />
                {proposal.reason && (
                    <Text
                        size="medium"
                        color="text-weak"
                        margin={{ top: 'small', bottom: 'medium' }}
                        style={{ fontStyle: 'italic', lineHeight: 1.4 }}
                    >
                        {proposal.reason}
                    </Text>
                    )}

            <Box direction="row" gap="small">
              <Button primary label="Looks good — Save" onClick={onConfirmSave} />
              <Button label="Try again" onClick={() => setProposal(null)} />
            </Box>

            {error && <Text color="status-critical">{error}</Text>}
          </Box>
        )}
      </Box>
      <BottomNav />
    </Box>
  )
}
