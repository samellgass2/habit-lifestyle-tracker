import { Box, Heading, Text } from 'grommet'
import { useAuth } from '../auth'

// The gateway serves this app only to signed-in adamOS sessions, so a missing
// user means the person isn't linked to a habits profile yet (or the habits
// database is unavailable) — say which, rather than showing a login form.
export default function ProtectedRoute({ children }) {
  const { user, loaded, reason } = useAuth()

  if (!loaded) return null

  if (!user) {
    const notLinked = reason === 'not_linked'
    return (
      <Box pad="large" gap="small">
        <Heading level={3} margin="none">
          {notLinked ? 'Almost there' : 'Habits is unavailable'}
        </Heading>
        <Text>
          {notLinked
            ? "You're signed in to adamOS, but your account isn't linked to a habits profile yet. Ask Sam to link it."
            : `The habit tracker couldn't load your profile (${reason || 'unknown'}). Try again in a minute.`}
        </Text>
      </Box>
    )
  }

  return children
}
