// src/pages/Inbox.jsx
import { useEffect, useState } from 'react'
import { Box, Heading, Text, Card, CardHeader, CardBody, Button } from 'grommet'
import { MailOption } from 'grommet-icons'
import { useNavigate } from 'react-router-dom'
import BottomNav from '../components/BottomNav'
import Toast from '../components/Toast'
import API from '../api'

// --- helpers copied from FriendFeed ---

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function AvatarCircle({ emoji, color }) {
  return (
    <Box
      width="40px"
      height="40px"
      round="full"
      align="center"
      justify="center"
      background={color || '#F5F3FF'}
      style={{ flexShrink: 0 }}
    >
      <Text style={{ fontSize: '22px' }}>{emoji || '🙂'}</Text>
    </Box>
  )
}

function kindBadge(kind) {
  if (kind === 'habit') return 'completed habit'
  if (kind === 'reward') return 'purchased reward'
  if (kind === 'reflection') return 'reflection'
  return ''
}

function kindAccentColor(kind) {
  if (kind === 'habit') return '#ECFDF5'
  if (kind === 'reward') return '#FEF3C7'
  if (kind === 'reflection') return '#EEF2FF'
  return '#F9FAFB'
}

// --- Inbox preview card for reactions/comments ---

function InboxActivityCard({ type, item }) {
  // type: 'reaction' | 'comment'
  const { actor, feed, reaction, comment, created_at } = item || {}

  const badge = feed?.feed_kind ? kindBadge(feed.feed_kind) : ''
  const bgColor =
    feed?.feed_kind === 'habit'
      ? feed?.accent_color || kindAccentColor(feed?.feed_kind)
      : kindAccentColor(feed?.feed_kind)

  let primaryLine
  if (type === 'reaction') {
    primaryLine = (
      <>
        <Text weight="bold">{actor?.username}</Text>
        <Text> reacted </Text>
        <Text weight="bold">{reaction}</Text>
        <Text> to your </Text>
        <Text weight="bold">
          {feed ? kindBadge(feed.feed_kind).toLowerCase() : 'post'}
        </Text>
      </>
    )
  } else {
    primaryLine = (
      <>
        <Text weight="bold">{actor?.username}</Text>
        <Text>{' commented on your '}</Text>
        <Text weight="bold">
          {feed ? kindBadge(feed.feed_kind).toLowerCase() : 'post'}
        </Text>
      </>
    )
  }

  return (
    <Card
      pad="medium"
      background="white"
      round="medium"
      margin={{ bottom: 'medium' }}
      border={{ color: '#E5E7EB' }}
      style={{
        boxShadow: '0 2px 6px rgba(0,0,0,0.05)',
        minHeight: '220px',          // 👈 prevent “thin” cards
        display: 'flex',             // 👈 make content stack nicely
        flexDirection: 'column',
      }}
    >
      <CardHeader justify="between" align="center" margin={{ bottom: 'small' }}>
        <Box direction="row" gap="small" align="center">
          <AvatarCircle emoji={actor?.emoji} color={actor?.accent_color} />
          <Box>
            <Box direction="row" wrap>
              {primaryLine}
            </Box>
            <Text size="xsmall" color="dark-3">
              {formatTime(created_at)}
            </Text>
          </Box>
        </Box>

        {feed?.feed_kind && (
          <Box
            pad={{ vertical: 'xxsmall', horizontal: 'small' }}
            round="large"
            background="#F3F4F6"
          >
            <Text size="xsmall" color="dark-3">
              {badge}
            </Text>
          </Box>
        )}
      </CardHeader>

      {feed && (
        <Box
          pad={{ vertical: 'small', horizontal: 'medium' }}
          round="small"
          background={bgColor}
          margin={{ bottom: 'small' }}
          gap="xsmall"
        >
          <Text weight="bold">{feed.title}</Text>
          {feed.subtitle && (
            <Text size="small" color="dark-2">
              {feed.subtitle}
            </Text>
          )}
        </Box>
      )}

      {type === 'comment' && comment && (
        <Box
          pad={{ vertical: 'xsmall', horizontal: 'small' }}
          background="#F9FAFB"
          round="small"
        >
          <Text size="small">
            <Text weight="bold">“</Text>
            <Text weight="bold">{comment}</Text>
            <Text weight="bold">”</Text>
          </Text>
        </Box>
      )}

      {type === 'reaction' && reaction && (
        <Box
          pad={{ vertical: 'xsmall', horizontal: 'small' }}
          background="#F9FAFB"
          round="small"
        >
          <Text size="small">Reaction: {reaction}</Text>
        </Box>
      )}
    </Card>
  )
}

// --- Friend request card ---

function FriendRequestCard({ fr, onDecision }) {
  const u = fr.other_user || {}
  const name = u.username || `User #${u.id}`
  const emoji = u.emoji || '🙂'
  const color = u.accent_color || 'brand'
  const msg = fr.message || 'No message included.'

  return (
    <Card pad="small" background="background-front">
      <CardHeader justify="between" align="center">
        <Box direction="row" gap="small" align="center">
          <AvatarCircle emoji={emoji} color={color} />
          <Box>
            <Text weight="bold">{name}</Text>
            <Text size="xsmall" color="dark-3">
              Friend request
            </Text>
          </Box>
        </Box>
        <Text size="small" color="status-warning">
          Pending
        </Text>
      </CardHeader>
      <CardBody>
        <Text size="small">{msg}</Text>
        <Box direction="row" gap="small" justify="end" margin={{ top: 'small' }}>
          <Button label="Reject" onClick={() => onDecision(fr, 'rejected')} />
          <Button primary label="Accept" onClick={() => onDecision(fr, 'accepted')} />
        </Box>
      </CardBody>
    </Card>
  )
}

function PendingActionCard({ item, onDecision }) {
  const creator = item.creator || {}
  const title = item.name || (item.type === 'habit' ? 'Habit' : 'Reward')

  const preview =
    item.type === 'habit'
      ? `${item.type_label || item.type} · ${item.challenge} · importance ${item.importance}`
      : `${item.cost_points} pts · ${item.is_recurring ? 'Recurring' : 'One-time'}`
  const note = item.notes || item.note

  const bg =
    item.type === 'habit'
      ? item.category_color || '#E5E7EB'
      : item.color || '#E5E7EB'
  const icon =
    item.type === 'habit'
      ? item.category_emoji || '✅'
      : item.emoji || '🎁'

  return (
    <Card pad="small" background="background-front" border={{ color: 'border' }}>
      <CardHeader justify="between" align="center">
        <Box direction="row" gap="small" align="center">
          <AvatarCircle emoji={creator.emoji || '🙂'} color={creator.color || 'brand'} />
          <Box>
            <Text weight="bold">{creator.name || `User #${creator.id || ''}`}</Text>
            <Text size="xsmall" color="dark-3">
              {item.type === 'habit' ? 'Habit request' : 'Reward request'}
            </Text>
          </Box>
        </Box>
        <Text size="small" color="text-weak">
          {formatTime(item.created_at_utc)}
        </Text>
      </CardHeader>
      <CardBody gap="xsmall">
        <Box direction="row" gap="small" align="center">
          <Box width="24px" height="24px" round="xsmall" style={{ background: bg }} />
          <Text weight="bold">
            {icon} {title}
          </Text>
        </Box>
        <Text size="small" color="dark-3">{preview}</Text>
        {note && (
          <Text size="small" color="dark-3">
            Note: {note}
          </Text>
        )}
        <Box direction="row" gap="small" justify="end" margin={{ top: 'small' }}>
          <Button
            label="Reject"
            onClick={() => onDecision(item, 'reject')}
            secondary
            color="status-critical"
          />
          <Button
            primary
            label="Accept"
            onClick={() => onDecision(item, 'accept')}
          />
        </Box>
      </CardBody>
    </Card>
  )
}

// --- Main Inbox page ---

export default function Inbox() {
  const nav = useNavigate()

  const [toast, setToast] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [friendRequests, setFriendRequests] = useState([])
  const [reactions, setReactions] = useState([])
  const [comments, setComments] = useState([])
  const [pendingActions, setPendingActions] = useState([])

  // load inbox + mark items as seen
  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      setError(null)
      try {
        const data = await API.getInbox()
        if (cancelled) return

        const fr = data.friend_requests || []
        const rs = data.reactions || []
        const cs = data.comments || []
        const pa = data.pending_actions || []

        setFriendRequests(fr)
        setReactions(rs)
        setComments(cs)
        setPendingActions(pa)

        const reactionIds = rs.map(r => r.id)
        const commentIds = cs.map(c => c.id)
        if (reactionIds.length || commentIds.length) {
          API.markInboxSeen({
            reaction_ids: reactionIds,
            comment_ids: commentIds,
          }).catch(e => console.error('markInboxSeen failed', e))
        }
      } catch (e) {
        console.error(e)
        if (!cancelled) setError('Could not load inbox.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [])

  async function handleRequestDecision(fr, decision /* 'accepted' | 'rejected' */) {
    try {
      await API.updateFriendship(fr.id, decision)
      const remaining = friendRequests.filter(r => r.id !== fr.id)
      setFriendRequests(remaining)
      setToast(
        decision === 'accepted'
          ? 'Friend request accepted.'
          : 'Friend request rejected.',
      )
    } catch (e) {
      console.error(e)
      setToast('Could not update friend request.')
    }
  }

  async function handlePendingAction(item, action) {
    try {
      await API.respondPendingAction(item.type, item.id, action)
      setPendingActions(prev => prev.filter(p => p.id !== item.id || p.type !== item.type))
      setToast(action === 'accept' ? 'Request accepted.' : 'Request rejected.')
    } catch (e) {
      console.error(e)
      setToast(e.message || 'Could not update request.')
    }
  }

  const hasNotifications =
    (reactions && reactions.length > 0) || (comments && comments.length > 0)

  return (
    <Box
      fill
      pad={{ bottom: '80px', horizontal: 'medium', top: 'large' }}
      gap="medium"
    >
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}

      <Box direction="row" align="center" gap="small">
        <MailOption />
        <Heading level={2} margin="none">
          Inbox
        </Heading>
      </Box>

      {error && (
        <Text size="small" color="status-critical">
          {error}
        </Text>
      )}
      {loading && (
        <Text size="small" color="dark-2">
          Loading inbox…
        </Text>
      )}

      {!loading && (
        <>
          {/* Pending actions */}
          <Heading level={3} margin={{ top: 'small', bottom: 'xsmall' }}>
            Habit & Reward Requests
          </Heading>
          {pendingActions.length === 0 ? (
            <Text size="small" color="dark-3">
              No pending requests.
            </Text>
          ) : (
            <Box gap="small" flex={false}>
              {pendingActions.map(p => (
                <PendingActionCard
                  key={`${p.type}-${p.id}`}
                  item={p}
                  onDecision={handlePendingAction}
                />
              ))}
            </Box>
          )}

          {/* Friend requests */}
          <Heading level={3} margin={{ top: 'small', bottom: 'xsmall' }}>
            Friend Requests
          </Heading>
          {friendRequests.length === 0 ? (
            <Text size="small" color="dark-3">
              No pending friend requests.
            </Text>
          ) : (
            <Box gap="small" flex={false}>   {/* 👈 don’t flex these */}
              {friendRequests.map(fr => (
                <FriendRequestCard
                  key={fr.id}
                  fr={fr}
                  onDecision={handleRequestDecision}
                />
              ))}
            </Box>
          )}

          {/* Reactions & comments */}
          <Heading level={3} margin={{ top: 'medium', bottom: 'xsmall' }}>
            Notifications
          </Heading>
          {!hasNotifications ? (
            <Text size="small" color="dark-3">
              No new reactions or comments.
            </Text>
          ) : (
            <Box gap="small" flex={false}>   {/* 👈 don’t flex these either */}
              {reactions.map(r => (
                <InboxActivityCard
                  key={`reaction-${r.id}`}
                  type="reaction"
                  item={r}
                />
              ))}
              {comments.map(c => (
                <InboxActivityCard
                  key={`comment-${c.id}`}
                  type="comment"
                  item={c}
                />
              ))}
            </Box>
          )}
        </>
      )}

      <Box direction="row" justify="start" margin={{ top: 'medium' }}>
        <Button label="Back to Me" onClick={() => nav('/account')} />
      </Box>

      <BottomNav />
    </Box>
  )
}
