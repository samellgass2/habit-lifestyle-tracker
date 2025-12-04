// src/pages/SendAction.jsx
import { useEffect, useMemo, useState } from 'react'
import {
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Heading,
  Layer,
  RadioButtonGroup,
  Select,
  Text,
  TextInput,
  TextArea,
  CheckBox,
} from 'grommet'
import { Add, Close, FormNext, FormPrevious } from 'grommet-icons'
import BottomNav from '../components/BottomNav'
import Toast from '../components/Toast'
import API from '../api'
import WeekdayPicker from '../components/WeekdayPicker'
import EmojiPicker from '../components/EmojiPicker'
import ColorPicker from '../components/ColorPicker'

const CHALLENGE_OPTIONS = ['automatic', 'easy', 'difficult', 'hard', 'daunting']
const IMPORTANCE_OPTIONS = [
  { label: 'No biggie', value: 1 },
  { label: 'Important', value: 2 },
  { label: 'Super important', value: 3 },
]

function AvatarCircle({ emoji, color, size = 26 }) {
  return (
    <Box
      width={`${size}px`}
      height={`${size}px`}
      round="full"
      align="center"
      justify="center"
      background={color || '#E5E7EB'}
      style={{ flexShrink: 0 }}
    >
      <Text size="small">{emoji || '🙂'}</Text>
    </Box>
  )
}

function PendingCard({ item }) {
  const recipient = item.recipient?.name || `User #${item.user_id}`
  const bg =
    item.type === 'habit'
      ? item.category_color || '#E5E7EB'
      : item.color || '#E5E7EB'
  const icon =
    item.type === 'habit'
      ? item.category_emoji || '✅'
      : item.emoji || '🎁'
  const note = item.note
  return (
    <Card pad="small" background="background-front" border={{ color: 'border' }}>
      <CardHeader direction="row" justify="between" align="center" pad={{ bottom: 'xsmall' }}>
        <Text weight="bold">{item.type === 'habit' ? 'Habit' : 'Reward'}</Text>
        <Text size="small" color="text-weak">
          to {recipient}
        </Text>
      </CardHeader>
      <CardBody gap="xxsmall">
        <Box direction="row" gap="small" align="center">
          <Box width="20px" height="20px" round="xsmall" style={{ background: bg }} />
          <Text weight="bold">
            {icon} {item.name}
          </Text>
        </Box>
        {item.type === 'habit' ? (
          <Text size="small" color="text-weak">
            {item.type_label} · {item.challenge} · importance {item.importance}
          </Text>
        ) : (
          <Text size="small" color="text-weak">
            {item.cost_points} pts · {item.is_recurring ? 'Recurring' : 'One-time'}
          </Text>
        )}
        {note && (
          <Text size="xsmall" color="text-weak">
            Note: {note}
          </Text>
        )}
        <Text size="xsmall" color="text-weak">
          Sent by you · awaiting acceptance
        </Text>
      </CardBody>
    </Card>
  )
}

function FriendPicker({ friends, value, onChange }) {
  const [query, setQuery] = useState('')
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return friends
    return friends.filter(f => (f.name || '').toLowerCase().includes(q))
  }, [query, friends])

  return (
    <Box gap="small">
      <TextInput
        placeholder="Filter friends"
        value={query}
        onChange={e => setQuery(e.target.value)}
      />
      <Box gap="xsmall" style={{ maxHeight: '220px', overflowY: 'auto' }}>
        {filtered.map(u => (
          <Card
            key={u.id}
            pad="xsmall"
            background={value?.id === u.id ? 'accent-1' : 'background-back'}
            onClick={() => onChange(u)}
          >
            <Box direction="row" gap="small" align="center">
              <AvatarCircle emoji={u.emoji} color={u.color} size={36} />
              <Text>{u.name}</Text>
            </Box>
          </Card>
        ))}
        {filtered.length === 0 && (
          <Text size="small" color="text-weak">
            No friends found.
          </Text>
        )}
      </Box>
    </Box>
  )
}

function HabitForm({
  categories,
  value,
  onChange,
}) {
  const catOptions = categories.map(c => ({
    ...c,
    optionLabel: `${c.emoji || '📁'} ${c.category_name} (${c.points_mode})`,
  }))
  const selectedCategory = useMemo(
    () => categories.find(c => c.id === value.category_id) || null,
    [categories, value.category_id]
  )
  const pointsMode = selectedCategory?.points_mode || 'tasks'

  return (
    <Box gap="small">
      <TextInput
        placeholder="Habit name"
        value={value.name}
        onChange={e => onChange({ ...value, name: e.target.value })}
      />

      <Select
        options={catOptions}
        labelKey="optionLabel"
        valueKey={{ key: 'id', reduce: true }}
        value={value.category_id}
        onChange={({ option }) => onChange({ ...value, category_id: option.id })}
        placeholder="Select category"
      />

      <RadioButtonGroup
        direction="row"
        options={[
          { label: 'Recurring', value: 'recurring' },
          { label: 'One-off', value: 'one-off' },
        ]}
        value={value.type}
        onChange={e => onChange({ ...value, type: e.target.value })}
      />

      {value.type === 'one-off' && (
        <TextInput
          type="date"
          value={value.date_local}
          onChange={e => onChange({ ...value, date_local: e.target.value })}
        />
      )}

      <Select
        options={CHALLENGE_OPTIONS}
        value={value.challenge}
        onChange={({ option }) => onChange({ ...value, challenge: option })}
      />

      <Select
        options={IMPORTANCE_OPTIONS}
        labelKey="label"
        valueKey={{ key: 'value', reduce: true }}
        value={value.importance}
        onChange={({ option }) => onChange({ ...value, importance: option.value })}
      />

      {pointsMode === 'time' && (
        <TextInput
          type="number"
          placeholder="Target minutes"
          value={value.time_minutes}
          onChange={e => onChange({ ...value, time_minutes: e.target.value })}
        />
      )}
      {pointsMode === 'percent' && (
        <TextInput
          type="number"
          placeholder="Target percent"
          value={value.percent_target}
          onChange={e => onChange({ ...value, percent_target: e.target.value })}
        />
      )}

      <Box direction="row" align="center" gap="small">
        <Text size="small">Parts per day:</Text>
        <Button
          label="-"
          onClick={() => onChange({ ...value, instances: Math.max(1, (Number(value.instances) || 1) - 1) })}
          size="small"
        />
        <Box pad={{ horizontal: 'small', vertical: 'xsmall' }} border round="xsmall">
          <Text>{Number(value.instances) || 1}</Text>
        </Box>
        <Button
          label="+"
          onClick={() => onChange({ ...value, instances: Math.min(10, (Number(value.instances) || 1) + 1) })}
          size="small"
        />
      </Box>

      {value.type !== 'one-off' && (
        <Box width="100%">
          <WeekdayPicker value={value.schedule || []} onChange={arr => onChange({ ...value, schedule: arr })} />
        </Box>
      )}

      <TextArea
        placeholder="Notes (optional)"
        value={value.notes}
        onChange={e => onChange({ ...value, notes: e.target.value })}
      />
    </Box>
  )
}

function RewardForm({ value, onChange }) {
  const [emojiOpen, setEmojiOpen] = useState(false)
  const [colorOpen, setColorOpen] = useState(false)

  return (
    <Box gap="small">
      <Box direction="row" gap="small" align="center">
        <Button onClick={() => setEmojiOpen(true)} plain>
          <Box pad="xsmall" round="xsmall" border>
            <Text style={{ fontSize: 20 }}>{value.emoji || '🎁'}</Text>
          </Box>
        </Button>
        <EmojiPicker
          value={value.emoji}
          open={emojiOpen}
          onChange={e => onChange({ ...value, emoji: e })}
          onClose={() => setEmojiOpen(false)}
        />
        <TextInput
          placeholder="Reward name"
          value={value.name}
          onChange={e => onChange({ ...value, name: e.target.value })}
        />
      </Box>

      <Button plain onClick={() => setColorOpen(true)} title={value.color || '#E5E7EB'}>
        <Box direction="row" gap="xsmall" align="center">
          <Box width="28px" height="20px" round="xsmall" border={{ color: 'border' }} style={{ background: value.color || '#E5E7EB' }} />
          <Text size="small" color="text-weak">{value.color || '#E5E7EB'}</Text>
        </Box>
      </Button>
      <ColorPicker
        value={value.color || '#E5E7EB'}
        open={colorOpen}
        onClose={() => setColorOpen(false)}
        onChange={(hex) => onChange({ ...value, color: hex })}
        title="Choose reward color"
      />

      <TextInput
        type="number"
        placeholder="Cost in points"
        value={value.cost_points}
        onChange={e => onChange({ ...value, cost_points: e.target.value })}
      />
      <TextArea
        placeholder="Note to recipient (optional)"
        value={value.note || ''}
        onChange={e => onChange({ ...value, note: e.target.value })}
      />
      <CheckBox
        label="Recurring"
        checked={!!value.is_recurring}
        onChange={e => onChange({ ...value, is_recurring: e.target.checked })}
      />
    </Box>
  )
}

function CreatePendingActionLayer({ onClose, onCreated }) {
  const [friends, setFriends] = useState([])
  const [recipient, setRecipient] = useState(null)
  const [categories, setCategories] = useState([])
  const [type, setType] = useState('habit')
  const [step, setStep] = useState('form')
  const [toast, setToast] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const [habit, setHabit] = useState({
    name: '',
    type: 'recurring',
    date_local: new Date().toISOString().slice(0, 10),
    challenge: 'easy',
    importance: 1,
    time_minutes: '',
    percent_target: '',
    instances: 1,
    notes: '',
    category_id: null,
    schedule: [],
  })

  const [reward, setReward] = useState({
    name: '',
    emoji: '🎁',
    color: '#E5E7EB',
    cost_points: '10',
    is_recurring: false,
  })

  useEffect(() => {
    let alive = true
    async function loadFriends() {
      const data = await API.getFriendships('accepted')
      if (!alive) return
      const users = (data.friendships || []).map(fr => ({
        id: fr.other_user?.id ?? fr.other_user_id,
        name: fr.other_user?.name ?? `Friend #${fr.other_user_id}`,
        emoji: fr.other_user?.emoji ?? '🙂',
        color: fr.other_user?.color ?? 'brand',
      }))
      setFriends(users)
    }
    loadFriends()
    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    let alive = true
    async function loadCategoriesForRecipient(rid) {
      if (!rid) return
      try {
        const data = await API.getFriendCategories(rid)
        if (!alive) return
        const cats = data.categories || []
        setCategories(cats)
        setHabit(h => ({ ...h, category_id: cats[0]?.id || null }))
      } catch (e) {
        console.error(e)
        if (alive) setCategories([])
      }
    }
    loadCategoriesForRecipient(recipient?.id)
    return () => {
      alive = false
    }
  }, [recipient?.id])

  const selectedCategory = useMemo(
    () => categories.find(c => c.id === habit.category_id) || null,
    [categories, habit.category_id]
  )
  const pointsMode = selectedCategory?.points_mode || 'tasks'

  const previewBg =
    type === 'habit'
      ? selectedCategory?.color || '#E5E7EB'
      : reward.color || '#E5E7EB'
  const previewEmoji =
    type === 'habit'
      ? selectedCategory?.emoji || '✅'
      : reward.emoji || '🎁'

  function validate() {
    if (!recipient) return 'Pick a recipient'
    if (type === 'habit') {
      if (!habit.name.trim()) return 'Name required'
      if (!habit.category_id) return 'Pick a category'
      if (pointsMode === 'time' && !habit.time_minutes) return 'Minutes required'
      if (pointsMode === 'percent' && !habit.percent_target) return 'Percent required'
      if (habit.type === 'one-off' && !habit.date_local) return 'Pick a date'
    } else {
      if (!reward.name.trim()) return 'Name required'
      if (!reward.cost_points) return 'Cost required'
    }
    return null
  }

  async function submit() {
    const err = validate()
    if (err) {
      setToast(err)
      return
    }
    if (step === 'form') {
      setStep('confirm')
      return
    }

    const payload =
      type === 'habit'
        ? {
            type,
            recipient_user_id: recipient.id,
            name: habit.name.trim(),
            habit_type: habit.type,
            category_id: habit.category_id,
            date_local: habit.type === 'one-off' ? habit.date_local : null,
            challenge: habit.challenge,
            importance: Number(habit.importance) || 1,
            time_minutes: habit.time_minutes ? Number(habit.time_minutes) : undefined,
            percent_target: habit.percent_target ? Number(habit.percent_target) : undefined,
            instances: Number(habit.instances) || 1,
            notes: habit.notes?.trim() || undefined,
            schedule: habit.schedule || [],
          }
        : {
            type,
            recipient_user_id: recipient.id,
            name: reward.name.trim(),
            emoji: reward.emoji || '🎁',
            color: reward.color || '#E5E7EB',
            cost_points: Number(reward.cost_points),
            note: reward.note?.trim() || undefined,
            is_recurring: reward.is_recurring,
          }

    setSubmitting(true)
    try {
      await API.createPendingAction(payload)
      onCreated && onCreated()
      onClose && onClose()
    } catch (e) {
      console.error(e)
      setToast(e.message || 'Failed to send')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Layer
      onEsc={() => !submitting && onClose()}
      onClickOutside={() => !submitting && onClose()}
      responsive={false}
    >
      <Box pad="medium" gap="medium" width="large">
        <Box direction="row" justify="between" align="center">
          <Heading level={4} margin="none">
            Send a {type}
          </Heading>
          <Button icon={<Close />} onClick={() => !submitting && onClose()} />
        </Box>

        {toast && <Toast message={toast} onClose={() => setToast(null)} />}

        <Box direction="row" gap="medium" wrap>
          <Box flex="grow" basis="50%">
            <Text size="small" weight="bold">
              Recipient
            </Text>
            <FriendPicker friends={friends} value={recipient} onChange={setRecipient} />
          </Box>

          <Box flex="grow" basis="45%" gap="small">
            <Box gap="xsmall">
              <Text size="small" weight="bold">
                Type
              </Text>
              <RadioButtonGroup
                direction="row"
                options={[
                  { label: 'Habit', value: 'habit' },
                  { label: 'Reward', value: 'reward' },
                ]}
                value={type}
                onChange={e => {
                  setType(e.target.value)
                  setStep('form')
                }}
              />
            </Box>

            {type === 'habit' ? (
              <HabitForm
                categories={categories}
                value={habit}
                onChange={setHabit}
              />
            ) : (
              <RewardForm value={reward} onChange={setReward} />
            )}
          </Box>
        </Box>

        {step === 'confirm' && (
          <Box pad="small" background="background-contrast" round="small" gap="xsmall">
            <Text size="small" color="text-weak">
              Preview for {recipient?.name || 'recipient'}
            </Text>
            <Box direction="row" gap="small" align="center">
              <Box width="24px" height="24px" round="xsmall" style={{ background: previewBg }} />
              <Text weight="bold">
                {previewEmoji} {type === 'habit' ? habit.name : reward.name}
              </Text>
            </Box>
            {type === 'habit' ? (
              <Text size="small" color="text-weak">
                Challenge {habit.challenge} · importance {habit.importance} ·{' '}
                {habit.type === 'one-off' ? `on ${habit.date_local}` : 'recurring'}
              </Text>
            ) : (
              <Text size="small" color="text-weak">
                Costs {reward.cost_points} pts ·{' '}
                {reward.is_recurring ? 'recurring' : 'one-time'}
              </Text>
            )}
            {type === 'reward' && reward.note && (
              <Text size="small" color="text-weak">
                Note: {reward.note}
              </Text>
            )}
            {type === 'habit' && habit.notes && (
              <Text size="small" color="text-weak">
                Note: {habit.notes}
              </Text>
            )}
          </Box>
        )}

        <Box direction="row" justify="between" align="center">
          <Button
            icon={<FormPrevious />}
            label="Edit"
            onClick={() => setStep('form')}
            disabled={step === 'form' || submitting}
          />
          <Box direction="row" gap="small">
            <Button label="Cancel" onClick={() => !submitting && onClose()} />
            <Button
              primary
              icon={step === 'form' ? <FormNext /> : undefined}
              label={submitting ? 'Sending…' : step === 'form' ? 'Review' : 'Send'}
              onClick={submit}
              disabled={submitting}
            />
          </Box>
        </Box>
      </Box>
    </Layer>
  )
}

export default function SendAction() {
  const [pending, setPending] = useState([])
  const [toast, setToast] = useState(null)
  const [showCreate, setShowCreate] = useState(false)

  async function load() {
    try {
      const data = await API.getPendingActions('outbound')
      setPending(data.pending || [])
    } catch (e) {
      console.error(e)
      setToast('Could not load pending actions')
    }
  }

  useEffect(() => {
    load()
  }, [])

  return (
    <Box fill>
      <Box
        flex
        overflow="auto"
        style={{ minHeight: 0 }}
        pad={{ horizontal: 'medium', top: 'small' }}
        gap="medium"
      >
        {toast && <Toast message={toast} onClose={() => setToast(null)} />}

        <Box height="30px" />
        <Box direction="row" justify="between" align="center">
          <Heading level={3} margin="none">
            Send
          </Heading>
          <Button icon={<Add />} onClick={() => setShowCreate(true)} plain />
        </Box>
        <Text size="small" color="text-weak">
          Actions you’ve sent to friends (awaiting response).
        </Text>

        {pending.length === 0 ? (
          <Box
            background="background"
            round="small"
            pad="medium"
            border={{ color: 'border' }}
          >
            <Text>No pending actions yet.</Text>
            <Button
              label="Send one"
              onClick={() => setShowCreate(true)}
              margin={{ top: 'small' }}
            />
          </Box>
        ) : (
          <Box gap="small">
            {pending.map(p => (
              <PendingCard key={`${p.type}-${p.id}`} item={p} />
            ))}
          </Box>
        )}

        <Box height="220px" />
        <Box flex={false} height="0" style={{ height: 'calc(140px + env(safe-area-inset-bottom, 0px))' }} />
      </Box>

      <BottomNav />
      {showCreate && (
        <CreatePendingActionLayer
          onClose={() => setShowCreate(false)}
          onCreated={load}
        />
      )}
    </Box>
  )
}
