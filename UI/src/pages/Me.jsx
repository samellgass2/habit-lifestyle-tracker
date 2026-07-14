import { Box, Button, Heading, Text } from 'grommet'
import { MailOption, Group } from 'grommet-icons'
import { useNavigate, useLocation } from 'react-router-dom'
import { useEffect, useState, useMemo } from 'react'
import BottomNav from '../components/BottomNav'
import Toast from '../components/Toast'
import API from '../api'
import UserSummaryCard from '../components/UserSummaryCard'
import FriendFeed from '../components/FriendFeed'

export default function Me() {
  const nav = useNavigate()
  const location = useLocation()

  const [toast, setToast] = useState(null)
  const [me, setMe] = useState(null)

  const [hasNotifications, setHasNotifications] = useState(false)
  const [friends, setFriends] = useState([])

  const [loadingFriends, setLoadingFriends] = useState(true)
  const [friendsError, setFriendsError] = useState(null)

  const [summaries, setSummaries] = useState({})
  const [loadingSummaries, setLoadingSummaries] = useState(false)

  // Handle toast from navigation state
  useEffect(() => {
    if (location.state?.toast) {
      setToast(location.state.toast)
      nav(location.pathname, { replace: true, state: {} })
    }
  }, [location, nav])

  // Load "me"
  useEffect(() => {
    let cancelled = false
    async function loadMe() {
      try {
        const data = await API.me()
        if (!cancelled && data.authenticated && data.user) {
          setMe(data.user)
        }
      } catch (e) {
        console.error(e)
      }
    }
    loadMe()
    return () => {
      cancelled = true
    }
  }, [])

  // Load friendships: pending (for badge) + accepted (for list)
  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoadingFriends(true)
      setFriendsError(null)

      try {
        const pending = await API.getFriendships('pending')
        const inboundPending = (pending.friendships || []).some(
          fr => fr.direction === 'incoming'
        )
        if (!cancelled) {
          setHasNotifications(inboundPending)
        }

        const accepted = await API.getFriendships('accepted')
        if (!cancelled) {
          setFriends(accepted.friendships || [])
        }
      } catch (e) {
        console.error(e)
        if (!cancelled) {
          setFriendsError('Could not load friends.')
        }
      } finally {
        if (!cancelled) {
          setLoadingFriends(false)
        }
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [])

  // Load summaries once we know me + friends
  useEffect(() => {
    if (!me) return

    const ids = new Set()
    ids.add(me.id)
    for (const fr of friends) {
      if (fr.other_user_id) ids.add(fr.other_user_id)
    }
    const idList = Array.from(ids)
    if (!idList.length) return

    let cancelled = false
    async function loadSummaries() {
      setLoadingSummaries(true)
      try {
        const data = await API.getUserSummaries(idList)
        if (!cancelled) {
          const map = {}
          for (const u of (data.users || [])) {
            map[u.id] = u
          }
          setSummaries(map)
        }
      } catch (e) {
        console.error(e)
      } finally {
        if (!cancelled) setLoadingSummaries(false)
      }
    }

    loadSummaries()
    return () => {
      cancelled = true
    }
  }, [me, friends])

  function renderFriendList() {
    if (loadingFriends && !friends.length) {
      return (
        <Box pad={{ vertical: 'small' }}>
          <Text size="small">Loading friends…</Text>
        </Box>
      )
    }

    if (friendsError) {
      return (
        <Box pad={{ vertical: 'small' }}>
          <Text size="small" color="status-critical">
            {friendsError}
          </Text>
        </Box>
      )
    }

    if (!friends.length) {
      return (
        <Box
          pad="medium"
          background="background-front"
          round="small"
          elevation="small"
          align="center"
          justify="center"
          gap="xsmall"
        >
          <Text weight="bold">Add your friends to track together!</Text>
          <Text size="small">
            Once you add friends, they’ll appear here with their own summary widgets.
          </Text>
        </Box>
      )
    }

    return (
      <Box gap="medium">
        {friends.map(fr => {
          const uid = fr.other_user_id
          const summary = summaries[uid]
          return <UserSummaryCard key={fr.id} summary={summary} />
        })}
      </Box>
    )
  }

  // compute feed user IDs: me + all other_user_id
  const feedUserIds = useMemo(() => {
    if (!me) return []
    const ids = new Set([me.id])
    for (const fr of friends) {
      if (fr.other_user_id) ids.add(fr.other_user_id)
    }
    return Array.from(ids)
  }, [me?.id, friends])

  const inboxLabel = hasNotifications ? 'Inbox (!)' : 'Inbox'

  // ---------- RENDER ----------

  return (
    <Box
      fill
      pad={{ bottom: '80px', horizontal: 'medium', top: 'large' }}
      gap="medium"
    >
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}

      <Box height="30px" />

      {/* Header */}
      <Heading level={1} margin="none">
        Me
      </Heading>

      <Box height="30px" />

      {/* User summary widget */}
      {me && summaries[me.id] ? (
        <UserSummaryCard summary={summaries[me.id]} />
      ) : (
        <Box
          pad="medium"
          background="background-front"
          round="small"
          elevation="small"
          gap="xsmall"
        >
          <Text size="small" weight="bold">
            User summary loading…
          </Text>
          {loadingSummaries && (
            <Text size="small">Fetching your recent activity.</Text>
          )}
        </Box>
      )}

      {/* Update profile button */}
      <Button label="Update Profile" onClick={() => nav('/me/profile')} />

      {/* Friends section header */}
      <Heading level={3} margin={{ top: 'medium', bottom: 'xsmall' }}>
        Friends
      </Heading>

      {/* Friends action buttons: inbox + manage friends */}
      <Box direction="row" gap="small" flex={false}>
        <Button
          icon={<MailOption />}
          label={inboxLabel}
          onClick={() => nav('/inbox')}
        />
        <Button
          icon={<Group />}
          label="Manage Friends"
          primary
          onClick={() => nav('/account/friends')}
        />
      </Box>

      {/* Friends list - non-flexing */}
      <Box gap="medium" flex={false}>
        {renderFriendList()}
      </Box>

      <Heading level={2} margin={{ top: 'medium', bottom: 'xsmall' }}>
        Feed
      </Heading>

      <FriendFeed userIds={feedUserIds} />

      <BottomNav />
    </Box>
  )
}
