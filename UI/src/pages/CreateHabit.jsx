// src/pages/CreateHabit.jsx
import { useEffect, useMemo, useState } from 'react'
import { Box, Button, Heading, Text, TextInput, RadioButtonGroup, Select } from 'grommet'
import { useNavigate } from 'react-router-dom'
import API from '../api'
import BottomNav from '../components/BottomNav'
import Toast from '../components/Toast'
import SliderWithTrack from '../components/SlideWithTrack'
import WeekdayPicker from '../components/WeekdayPicker'

const CHALLENGE_LABELS = ['automatic','easy','difficult','hard','daunting'] // 1..5
const IMPORTANCE_LABELS = ['no biggie','important','super important']       // 1..3

export default function CreateHabit() {
  const nav = useNavigate()
  const [toast, setToast] = useState(null)
  const [saving, setSaving] = useState(false)

  const [name, setName] = useState('')
  const [type, setType] = useState('recurring')
  const [dateLocal, setDateLocal] = useState(() => new Date().toISOString().split('T')[0])

  const [categories, setCategories] = useState([])
  const [categoryId, setCategoryId] = useState(null)

  // sliders (internal are numeric; backend expects enum for challenge, 1..3 for importance)
  const [challengeIdx, setChallengeIdx] = useState(2) // default "difficult" (index 2 -> value 3)
  const [importanceIdx, setImportanceIdx] = useState(0) // default 1

  const [timeMin, setTimeMin] = useState('30')
  const [percentTarget, setPercentTarget] = useState('100')

  const [schedule, setSchedule] = useState([])

  // NEW: instances per day (1–10)
  const [instances, setInstances] = useState(1)

  useEffect(() => {
    let alive = true
    API.listCategories().then(res => {
      if (!alive) return
      const cats = res.categories || []
      setCategories(cats)
      if (!categoryId && cats.length) setCategoryId(cats[0].id)
    })
    return () => { alive = false }
  }, [])

  const catOptions = categories.map(c => ({
    ...c,
    optionLabel: `${c.emoji || '📁'} ${c.category_name} (${c.points_mode})`,
  }))

  const selectedCategory = useMemo(
    () => categories.find(c => c.id === categoryId) || null,
    [categories, categoryId]
  )
  const pointsMode = selectedCategory?.points_mode || 'tasks'

  const save = async () => {
    if (!name.trim()) { setToast('Please enter a habit name'); return }
    if (!categoryId)   { setToast('Pick a category'); return }

    const challenge = CHALLENGE_LABELS[challengeIdx]            // enum string
    const importance = importanceIdx + 1                         // 1..3
    const body = {
      name: name.trim(),
      category_id: categoryId,
      type,
      date_local: type === 'one-off' ? dateLocal : null,
      challenge,
      importance,
      instances, // NEW
      // base_value hidden → let server default (1.0)
    }
    if (pointsMode === 'time')    body.time_minutes   = Number(timeMin || 0)
    if (pointsMode === 'percent') body.percent_target = Number(percentTarget || 0)

    if (type === 'recurring') {
      // If user left all unchecked, omit or send [] — backend will treat [] as “every day”
      body.schedule = schedule && schedule.length ? schedule : []
    }

    setSaving(true)
    try {
      await API.createHabit(body)
      nav('/track', { replace: true, state: { toast: 'Habit added!' } })
    } catch (e) {
      setToast(e?.message || 'Failed to create habit')
    } finally { setSaving(false) }
  }

  // NEW: preview rectangles for instances
  const instanceRects = Array.from({ length: instances }).map((_, i) => (
    <Box
      key={i}
      width="16px"
      height="8px"
      round="xsmall"
      background="text-weak"
      margin={{ right: 'xxsmall' }}
    />
  ))

  return (
    <Box fill pad={{ bottom: '64px', horizontal: 'medium', top: 'medium' }} gap="medium">
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
      <Heading level={3} margin="none">Add Habit</Heading>

      <Box gap="small">
        <Text size="small" weight="bold">Name</Text>
        <TextInput value={name} onChange={e => setName(e.target.value)} placeholder="e.g. 30m guitar practice" />
      </Box>

      <Box gap="small">
        <Text size="small" weight="bold">Category</Text>
        <Select
          options={catOptions}
          labelKey="optionLabel"
          valueKey={{ key: 'id', reduce: true }}  // value === categoryId (number)
          value={categoryId}                      // controlled by id
          onChange={({ option }) => setCategoryId(option.id)}
        />
      </Box>

      <Box gap="xsmall">
        <Text size="small" weight="bold">Type</Text>
        <RadioButtonGroup
          name="type" direction="row"
          options={[
            {label:'Recurring', value:'recurring'},
            {label:'One-off',   value:'one-off'}
          ]}
          value={type}
          onChange={e => setType(e.target.value)}
        />
      </Box>

      {type === 'one-off' && (
        <Box gap="small">
          <Text size="small" weight="bold">Date</Text>
          <TextInput type="date" value={dateLocal} onChange={e => setDateLocal(e.target.value)} />
        </Box>
      )}

      {type === 'recurring' && (
        <Box gap="small">
          <Text size="small" weight="bold">Schedule (days of week)</Text>
          <WeekdayPicker value={schedule} onChange={setSchedule} />
          <Text size="xsmall" color="text-weak">Tip: Leave empty for “every day”.</Text>
        </Box>
      )}

      {/* Challenge slider (1..5) */}
      <Box gap="xxsmall">
        <Text size="small" weight="bold">Challenge: {CHALLENGE_LABELS[challengeIdx]}</Text>
        <SliderWithTrack min={0} max={4} step={1} value={challengeIdx} onChange={e => setChallengeIdx(Number(e.target.value))} />
        <Box direction="row" justify="between"><Text size="xsmall">auto</Text><Text size="xsmall">daunting</Text></Box>
      </Box>

      {/* Importance slider (1..3) */}
      <Box gap="xxsmall">
        <Text size="small" weight="bold">Importance: {IMPORTANCE_LABELS[importanceIdx]}</Text>
        <SliderWithTrack min={0} max={2} step={1} value={importanceIdx} onChange={e => setImportanceIdx(Number(e.target.value))} />
        <Box direction="row" justify="between"><Text size="xsmall">1</Text><Text size="xsmall">3</Text></Box>
      </Box>

      {/* NEW: Instances slider + preview */}
      <Box gap="xxsmall">
        <Text size="small" weight="bold">
          Parts per day: {instances}
        </Text>
        <SliderWithTrack
          min={1}
          max={10}
          step={1}
          value={instances}
          onChange={e => setInstances(Number(e.target.value))}
        />
        <Box direction="row" align="center" margin={{ top: 'xxsmall' }}>
          {instanceRects}
        </Box>
        <Text size="xsmall" color="text-weak" margin={{ top: 'xxsmall' }}>
          Example: “3 glasses of water” → 3 parts; full points after all parts.
        </Text>
      </Box>

      {pointsMode === 'time' && (
        <Box gap="small" width="220px">
          <Text size="small" weight="bold">Target minutes</Text>
          <TextInput type="number" min="0" step="5" value={timeMin} onChange={e => setTimeMin(e.target.value)} />
        </Box>
      )}

      {pointsMode === 'percent' && (
        <Box gap="small" width="220px">
          <Text size="small" weight="bold">Target percent</Text>
          <TextInput type="number" min="0" max="100" step="5" value={percentTarget} onChange={e => setPercentTarget(e.target.value)} />
        </Box>
      )}

      <Box direction="row" gap="small" margin={{ top: 'small' }}>
        <Button primary label={saving ? 'Saving…' : 'Save'} onClick={save} disabled={saving} />
        <Button label="Cancel" onClick={() => nav('/track')} />
      </Box>

      <BottomNav />
    </Box>
  )
}
