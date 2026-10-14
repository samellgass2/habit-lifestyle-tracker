// src/components/FriendFeed.jsx
import { useEffect, useRef, useState } from 'react'
import { Box, Text, Button, Drop, TextInput } from 'grommet'
import API from '../api'

const PAGE_SIZE = 20

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
  if (kind === 'habit') return 'Habit completed'
  if (kind === 'reward') return 'Reward purchased'
  if (kind === 'reflection') return 'Reflection'
  return ''
}

function kindAccentColor(kind) {
  if (kind === 'habit') return '#ECFDF5'
  if (kind === 'reward') return '#FEF3C7'
  if (kind === 'reflection') return '#EEF2FF'
  return '#F9FAFB'
}

const DEFAULT_REACTION_CHOICES = ['👍', '🔥', '❤️', '🎉', '👏', '🤩']

function FeedCard({ item }) {
  const {
    feed_kind,
    feed_item_id,
    username,
    emoji,
    accent_color,
    user_color,
    title,
    subtitle,
    points_delta,
    event_time,
  } = item

  const [reactions, setReactions] = useState(null)
  const [comments, setComments] = useState([])
  const [commentsLoaded, setCommentsLoaded] = useState(false)
  const [commentText, setCommentText] = useState('')
  const [commentSubmitting, setCommentSubmitting] = useState(false)
  const [showReactionPicker, setShowReactionPicker] = useState(false)
  const [reactionsLoaded, setReactionsLoaded] = useState(false)

  const reactButtonRef = useRef()

  // --- data loading ---

  useEffect(() => {
    let cancelled = false
    async function loadReactions() {
      try {
        const data = await API.getFeedReactions(feed_kind, feed_item_id)
        if (!cancelled) setReactions(data)
      } catch (err) {
        console.error('Failed to load reactions', err)
      } finally {
        if (!cancelled) setReactionsLoaded(true)
      }
    }
    loadReactions()
    return () => { cancelled = true }
  }, [feed_kind, feed_item_id])

  useEffect(() => {
    let cancelled = false
    async function loadComments() {
      try {
        const data = await API.getFeedComments(feed_kind, feed_item_id)
        if (!cancelled) setComments(data.comments || [])
      } catch (err) {
        console.error('Failed to load comments', err)
      } finally {
        if (!cancelled) setCommentsLoaded(true)
      }
    }
    loadComments()
    return () => { cancelled = true }
  }, [feed_kind, feed_item_id])

  // --- handlers ---

  const handleReact = async (reactionEmoji) => {
    try {
      const data = await API.postFeedReaction(feed_kind, feed_item_id, reactionEmoji)
      setReactions(data)
      setShowReactionPicker(false)
    } catch (err) {
      console.error('Failed to post reaction', err)
    }
  }

  const handleAddComment = async () => {
    const text = commentText.trim()
    if (!text || commentSubmitting) return
    setCommentSubmitting(true)
    try {
      const data = await API.postFeedComment(feed_kind, feed_item_id, text)
      setComments(prev => [...prev, data])
      setCommentText('')
    } catch (err) {
      console.error('Failed to post comment', err)
    } finally {
      setCommentSubmitting(false)
    }
  }

  const kindColor = kindAccentColor(feed_kind)
  const hasComments = commentsLoaded && comments.length > 0
  const commentsBoxHeight = hasComments ? '220px' : '100px'

  return (
    <Box
      pad="medium"
      margin={{ bottom: 'large' }}       // more space between cards
      background="white"
      round="medium"
      border={{ color: '#E5E7EB' }}
      gap="medium"
      style={{
        boxShadow: '0 2px 6px rgba(0,0,0,0.05)',
        display: 'flex',
        flexDirection: 'column',
        minHeight: '260px',              // 👈 ALWAYS enforce min height
      }}
    >
      {/* Header */}
      <Box direction="row" gap="small" align="center">
        <AvatarCircle emoji={emoji} color={user_color} />
        <Box flex="grow">
          <Text weight="bold">{username}</Text>
          <Text size="small" color="dark-2">
            {formatTime(event_time)}
          </Text>
        </Box>
        {feed_kind && (
          <Box
            pad={{ vertical: 'xxsmall', horizontal: 'small' }}
            round="large"
            background="#F3F4F6"
          >
            <Text size="xsmall" color="dark-3">
              {kindBadge(feed_kind)}
            </Text>
          </Box>
        )}
      </Box>

      {/* Colored content block – height follows wrapped text */}
      <Box
        pad={{ vertical: 'medium', horizontal: 'medium' }}
        background={feed_kind == "habit" ? accent_color : kindAccentColor(feed_kind)}
        round="small"
        gap="xsmall"
      >
        <Text weight="bold">{title}</Text>
        {subtitle && (
          <Text size="small" color="dark-2">
            {subtitle}
          </Text>
        )}
      </Box>

      {/* Spacer between content and reactions */}
      <Box height="10px" />

      {/* Reactions row */}
      <Box
        direction="row"
        justify="between"
        align="center"
        pad={{ horizontal: 'xsmall', vertical: 'xxsmall' }}
      >
        <Box direction="row" gap="xsmall" align="center">
          {reactionsLoaded && reactions && reactions.reactions.length > 0 ? (
            reactions.reactions.map((r) => (
              <Box
                key={r.emoji}
                direction="row"
                gap="xxsmall"
                align="center"
                pad={{ vertical: 'xxsmall', horizontal: 'small' }}
                round="large"
                background="#F9FAFB"
              >
                <Text>{r.emoji}</Text>
                <Text size="small" color="dark-3">
                  {r.count}
                </Text>
              </Box>
            ))
          ) : (
            <Text size="small" color="dark-3">
              {reactionsLoaded ? 'No reactions yet' : 'Loading reactions…'}
            </Text>
          )}
        </Box>

        <Box direction="row" gap="small" align="center">
          {reactions?.my_reaction && (
            <Text size="small" color="dark-3">
              Your reaction: {reactions.my_reaction}
            </Text>
          )}
          <Button
            ref={reactButtonRef}
            size="small"
            label="React"
            onClick={() => setShowReactionPicker(v => !v)}
          />
        </Box>
      </Box>

      {showReactionPicker && reactButtonRef.current && (
        <Drop
          target={reactButtonRef.current}
          align={{ top: 'bottom', right: 'right' }}
          plain
          margin={{ top: 'xsmall' }}
        >
          <Box
            pad="xsmall"
            direction="row"
            gap="xsmall"
            background="white"
            round="small"
            border={{ color: '#E5E7EB' }}
            style={{ boxShadow: '0 2px 6px rgba(0,0,0,0.25)' }}
          >
            {DEFAULT_REACTION_CHOICES.map((e) => (
              <Button
                key={e}
                label={e}
                onClick={() => handleReact(e)}
                plain
              />
            ))}
          </Box>
        </Drop>
      )}

      {/* Comments section */}
      <Box
        pad={{ top: 'small' }}
        border={{ side: 'top', color: '#E5E7EB' }}
        gap="small"
        margin={{ top: 'small' }}
      >
        <Box
          height={commentsBoxHeight}
          overflow="auto"
          pad={{ right: 'small', vertical: 'xsmall' }}
          margin={{ bottom: 'small' }}
        >
          {!commentsLoaded ? (
            <Text size="small" color="dark-3">
              Loading comments…
            </Text>
          ) : comments.length === 0 ? (
            <Text size="small" color="dark-3">
              No comments yet. Be the first!
            </Text>
          ) : (
            comments.map((c) => (
              <Box
                key={c.id}
                margin={{ bottom: 'xsmall' }}
                pad={{ vertical: 'xxsmall' }}
                style={{ minHeight: '40px' }}
              >
                <Text size="small" weight="bold">
                  {c.username}{' '}
                  <Text size="xsmall" color="dark-3">
                    {c.time_local ? formatTime(c.time_local) : ''}
                  </Text>
                </Text>
                <Text size="small">{c.comment}</Text>
              </Box>
            ))
          )}
        </Box>

        <Box direction="row" align="center" gap="small">
          <TextInput
            plain={false}
            placeholder="Add a comment…"
            value={commentText}
            onChange={(e) => setCommentText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleAddComment()
              }
            }}
          />
          <Button
            size="small"
            label={commentSubmitting ? 'Posting…' : 'Post'}
            onClick={handleAddComment}
            disabled={commentSubmitting || !commentText.trim()}
          />
        </Box>
      </Box>
    </Box>
  )
}






export default function FriendFeed({ userIds }) {
  const [items, setItems] = useState([])
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const sentinelRef = useRef(null)

  // Reset when userIds change
  useEffect(() => {
    setItems([])
    setOffset(0)
    setHasMore(true)
    setError(null)
  }, [JSON.stringify(userIds)])

  // Load page whenever offset changes
  useEffect(() => {
    if (!userIds || userIds.length === 0) return
    if (!hasMore) return

    let cancelled = false

    async function loadPage() {
      try {
        setLoading(true)
        const data = await API.getUsersFeed(userIds, offset, PAGE_SIZE)
        if (cancelled) return
        const newItems = data.items || []
        setItems((prev) => [...prev, ...newItems])
        setHasMore(Boolean(data.has_more))
      } catch (err) {
        if (!cancelled) {
          console.error(err)
          setError('Failed to load feed.')
          setHasMore(false)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    loadPage()
    return () => {
      cancelled = true
    }
  }, [offset, hasMore, userIds])

  // Trigger next page when sentinel hits viewport
  useEffect(() => {
    if (!hasMore) return
    const el = sentinelRef.current
    if (!el) return

    const observer = new IntersectionObserver(
        (entries) => {
            const first = entries[0]
            if (first.isIntersecting && !loading && hasMore) {
            setOffset((prev) => prev + PAGE_SIZE)
            }
        },
        {
            threshold: 0,           // trigger when ~10% of sentinel is visible
            rootMargin: '0px 0px 100px 0px'
        }
    )

    observer.observe(el)
    return () => observer.disconnect()
  }, [sentinelRef, loading, hasMore])

  if (!userIds || userIds.length === 0) {
    return null
  }

  return (
    <Box>
      {items.map((item) => (
        <FeedCard
          key={`${item.feed_kind}:${item.feed_item_id}`}
          item={item}
        />
      ))}

      {error && (
        <Text size="small" color="status-error" margin={{ top: 'small' }}>
          {error}
        </Text>
      )}

      {/* Sentinel for infinite scroll */}
      <div
        ref={sentinelRef}
        style={{
          height: 200,
          minHeight: 200,
          marginTop: 0,
        }}
      />

      {loading && (
        <Text size="small" color="dark-2" margin={{ top: 'small' }}>
          Loading…
        </Text>
      )}

      {/* Everybody's favorite spacer */}
      <Box minHeight="250px"/>
    </Box>
  )
}
