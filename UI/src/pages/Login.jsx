// src/pages/Login.jsx
import { useState } from 'react'
import { useLocation, useNavigate, Link } from 'react-router-dom'
import { Box, Button, Card, CardBody, CardFooter, Heading, Text, TextInput } from 'grommet'
import { useAuth } from '../auth.jsx'

export default function Login() {
  const { login } = useAuth()
  const nav = useNavigate()
  const loc = useLocation()
  const from = loc.state?.from?.pathname || '/dashboard'

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState(null)
  const [loading, setLoading]   = useState(false)

  const onSubmit = async (e) => {
    e.preventDefault()
    setError(null); setLoading(true)
    try {
      await login(username, password)
      nav(from, { replace: true })
    } catch (err) {
      setError(err.message || 'Login failed')
    } finally { setLoading(false) }
  }

  return (
    <Box fill align="center" justify="center" pad="medium">
      <Card width="medium">
        <CardBody gap="small">
          <Heading level={3} margin={{ top: 'xsmall', bottom: 'small' }}>Sign in</Heading>
          <form onSubmit={onSubmit}>
            <Box gap="small">
              <Box gap="xxsmall">
                <Text size="small" weight={600}>Username</Text>
                <TextInput value={username} onChange={e => setUsername(e.target.value)} />
              </Box>
              <Box gap="xxsmall">
                <Text size="small" weight={600}>Password</Text>
                <TextInput type="password" value={password} onChange={e => setPassword(e.target.value)} />
              </Box>

              {error && <Text color="status-critical">{error}</Text>}

              <Button type="submit" label={loading ? 'Signing in…' : 'Sign in'} primary margin={{ top: 'small' }} />
            </Box>
          </form>
        </CardBody>
        <CardFooter justify="between">
          <Text size="small" color="text-weak">Don’t have an account?</Text>
          <Button as={Link} to="/create-account" label="Create account" />
        </CardFooter>
      </Card>
    </Box>
  )
}
