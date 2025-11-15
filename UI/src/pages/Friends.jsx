// src/pages/Friends.jsx
import React, { useEffect, useState } from 'react'
import {
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Heading,
  Layer,
  Spinner,
  Text,
  TextArea,
  TextInput,
} from 'grommet'
import { FormAdd, Checkmark, Clock, Close } from 'grommet-icons'
import BottomNav from '../components/BottomNav'
import Toast from '../components/Toast'
import API from '../api'

function statusIcon(friendship) {
  if (!friendship) return <FormAdd />
  if (friendship.status === 'accepted') return <Checkmark />
  if (friendship.status === 'pending') return <Clock />
  return <FormAdd /> // 'rejected' behaves like "can re-request"
}

export default function Friends() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [toast, setToast] = useState(null)

  const [selected, setSelected] = useState(null) // { id, name, emoji, color, friendship }
  const [message, setMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // 🔹 On mount, load accepted friendships for default view
  useEffect(() => {
    let cancelled = false

    async function loadAccepted() {
      setLoading(true)
      setError(null)
      try {
        const data = await API.getFriendships('accepted')
        // Expect friendships with attached other_user
        const users = (data.friendships || []).map(fr => ({
          id: fr.other_user?.id ?? fr.other_user_id,
          name: fr.other_user?.name ?? `Friend #${fr.other_user_id}`,
          emoji: fr.other_user?.emoji ?? '🙂',
          color: fr.other_user?.color ?? 'brand',
          friendship: fr,
        }))
        if (!cancelled) {
          setResults(users)
        }
      } catch (err) {
        console.error(err)
        if (!cancelled) setError('Could not load friends.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    loadAccepted()
    return () => {
      cancelled = true
    }
  }, [])

  async function handleSearch(e) {
    e.preventDefault()
    setError(null)
    setToast(null)

    const trimmed = query.trim()

    // If query is empty, fall back to accepted list again
    if (!trimmed) {
      // reload accepted friends
      try {
        setLoading(true)
        const data = await API.getFriendships('accepted')
        const users = (data.friendships || []).map(fr => ({
          id: fr.other_user?.id ?? fr.other_user_id,
          name: fr.other_user?.name ?? `Friend #${fr.other_user_id}`,
          emoji: fr.other_user?.emoji ?? '🙂',
          color: fr.other_user?.color ?? 'brand',
          friendship: fr,
        }))
        setResults(users)
      } catch (err) {
        console.error(err)
        setError('Could not load friends.')
      } finally {
        setLoading(false)
      }
      return
    }

    setLoading(true)
    try {
      const data = await API.searchUsers(trimmed)
      setResults(data.users || [])
    } catch (err) {
      console.error(err)
      setError('Could not search users.')
    } finally {
      setLoading(false)
    }
  }

  function openManage(user) {
    setSelected(user)
    setMessage('')
  }

  function updateResultFriendship(userId, friendship) {
    setResults(prev =>
      prev.map(u => (u.id === userId ? { ...u, friendship } : u))
    )
  }

  async function sendRequest() {
    if (!selected) return
    setSubmitting(true)
    setError(null)
    try {
      const { friendship } = await API.createFriendRequest(
        selected.id,
        message.trim() || null,
      )
      updateResultFriendship(selected.id, friendship)
      setToast('Friend request sent.')
      setSelected(null)
    } catch (err) {
      console.error(err)
      setError(err.message || 'Could not send request.')
    } finally {
      setSubmitting(false)
    }
  }

  async function acceptOrReject(status) {
    if (!selected || !selected.friendship) return
    setSubmitting(true)
    setError(null)
    try {
      const { friendship } = await API.updateFriendship(
        selected.friendship.id,
        status,
      )
      updateResultFriendship(selected.id, friendship)
      setToast(
        status === 'accepted'
          ? 'Friend request accepted.'
          : 'Friend request rejected.',
      )
      setSelected(null)
    } catch (err) {
      console.error(err)
      setError(err.message || 'Could not update friendship.')
    } finally {
      setSubmitting(false)
    }
  }

  async function deleteFriendship() {
    if (!selected || !selected.friendship) return
    setSubmitting(true)
    setError(null)
    try {
      await API.deleteFriendship(selected.friendship.id)
      updateResultFriendship(selected.id, null)
      setToast('Friendship removed.')
      setSelected(null)
    } catch (err) {
      console.error(err)
      setError(err.message || 'Could not remove friendship.')
    } finally {
      setSubmitting(false)
    }
  }

  function renderManageLayer() {
    if (!selected) return null
    const friendship = selected.friendship

    const isPending = friendship && friendship.status === 'pending'
    const isAccepted = friendship && friendship.status === 'accepted'
    const isOutgoing = isPending && friendship.direction === 'outgoing'
    const isIncoming = isPending && friendship.direction === 'incoming'

    return (
      <Layer
        onEsc={() => !submitting && setSelected(null)}
        onClickOutside={() => !submitting && setSelected(null)}
        responsive={false}
      >
        <Box pad="medium" gap="medium" width="medium">
          <Box direction="row" justify="between" align="center">
            <Heading level={4} margin="none">
              {selected.name}
            </Heading>
            <Button icon={<Close />} onClick={() => !submitting && setSelected(null)} />
          </Box>

          <Box direction="row" align="center" gap="small">
            <Box
              width="40px"
              height="40px"
              round="full"
              background={selected.color || 'brand'}
              align="center"
              justify="center"
            >
              <Text size="large">{selected.emoji || '🙂'}</Text>
            </Box>
            <Text>
              {friendship
                ? `Status: ${friendship.status} (${friendship.direction})`
                : 'No current friendship.'}
            </Text>
          </Box>

          {/* Actions */}
          {!friendship && (
            <>
              <Text>Send a friend request with an optional message:</Text>
              <TextArea
                value={message}
                onChange={e => setMessage(e.target.value)}
                placeholder="Hey! Let's share our habit progress."
              />
              <Box direction="row" gap="small" justify="end">
                <Button
                  label="Cancel"
                  onClick={() => !submitting && setSelected(null)}
                  disabled={submitting}
                />
                <Button
                  primary
                  label={submitting ? 'Sending…' : 'Send Request'}
                  onClick={sendRequest}
                  disabled={submitting}
                />
              </Box>
            </>
          )}

          {isOutgoing && (
            <Box gap="small">
              <Text>You sent this friend request. You can cancel it.</Text>
              <Box direction="row" gap="small" justify="end">
                <Button
                  label={submitting ? 'Cancelling…' : 'Cancel Request'}
                  onClick={deleteFriendship}
                  disabled={submitting}
                  secondary
                />
              </Box>
            </Box>
          )}

          {isIncoming && (
            <Box gap="small">
              <Text>This user sent you a friend request.</Text>
              <Box direction="row" gap="small" justify="end">
                <Button
                  label={submitting ? 'Rejecting…' : 'Reject'}
                  onClick={() => acceptOrReject('rejected')}
                  disabled={submitting}
                />
                <Button
                  primary
                  label={submitting ? 'Accepting…' : 'Accept'}
                  onClick={() => acceptOrReject('accepted')}
                  disabled={submitting}
                />
              </Box>
            </Box>
          )}

          {isAccepted && (
            <Box gap="small">
              <Text>You are friends. You can remove this friendship.</Text>
              <Box direction="row" gap="small" justify="end">
                <Button
                  label={submitting ? 'Removing…' : 'Remove Friend'}
                  onClick={deleteFriendship}
                  disabled={submitting}
                  secondary
                />
              </Box>
            </Box>
          )}
        </Box>
      </Layer>
    )
  }

  return (
    <Box fill pad={{ bottom: '64px', horizontal: 'medium', top: 'medium' }} gap="medium">
      <Heading level={3} margin="none">Manage Friends</Heading>

      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
      {error && <Text color="status-critical">{error}</Text>}

      <Box
        as="form"
        onSubmit={handleSearch}
        direction="row"
        gap="small"
        align="center"
      >
        <TextInput
          placeholder="Search by name"
          value={query}
          onChange={e => setQuery(e.target.value)}
        />
        <Button type="submit" label="Search" disabled={loading} />
      </Box>

      {loading && (
        <Box pad="small">
          <Spinner />
        </Box>
      )}

      <Box gap="small">
        {results.map(user => (
          <Card
            key={user.id}
            onClick={() => openManage(user)}
            pad="small"
            background="background-front"
          >
            <CardHeader justify="between" align="center">
              <Box direction="row" gap="small" align="center">
                <Box
                  width="40px"
                  height="40px"
                  round="full"
                  background={user.color || 'brand'}
                  align="center"
                  justify="center"
                >
                  <Text size="large">{user.emoji || '🙂'}</Text>
                </Box>
                <Text weight="bold">{user.name}</Text>
              </Box>
              {statusIcon(user.friendship)}
            </CardHeader>
            <CardBody>
              {user.friendship ? (
                <Text size="small">
                  {user.friendship.status === 'accepted' && 'Friend'}
                  {user.friendship.status === 'pending' &&
                    (user.friendship.direction === 'outgoing'
                      ? 'Request sent'
                      : 'Request received')}
                </Text>
              ) : (
                <Text size="small">Tap to send a friend request</Text>
              )}
            </CardBody>
          </Card>
        ))}

        {!loading && results.length === 0 && (
          <Text size="small">No users found.</Text>
        )}
      </Box>

      {renderManageLayer()}
      <BottomNav />
    </Box>
  )
}
