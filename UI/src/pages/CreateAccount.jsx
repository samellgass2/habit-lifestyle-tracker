// src/pages/CreateAccount.jsx
import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Box, Button, Card, CardBody, CardFooter, Heading, Text, TextInput } from 'grommet'
import API from '../api'

export default function CreateAccount() {
  const nav = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [password2, setPassword2] = useState('')
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const onSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    if (password !== password2) { setError('Passwords do not match'); return }
    setLoading(true)
    try {
      await API.createUser(username, password, password2)
      nav('/login', { replace: true })
    } catch (err) {
      setError(err.error || 'Could not create account')
    } finally { setLoading(false) }
  }

  return (
    <Box fill align="center" justify="center" pad="medium">
      <Card width="medium">
        <CardBody gap="small">
          <Heading level={3} margin={{ top: 'xsmall', bottom: 'small' }}>Create account</Heading>
          <form onSubmit={onSubmit}>
            <Box gap="small">
              <LabeledInput label="Username" value={username} onChange={setUsername} />
              <LabeledInput label="Password" type="password" value={password} onChange={setPassword} />
              <LabeledInput label="Re-enter password" type="password" value={password2} onChange={setPassword2} />
              {error && <Text color="status-critical">{error}</Text>}
              <Button type="submit" label={loading ? 'Creating…' : 'Create account'} primary margin={{ top: 'small' }} />
            </Box>
          </form>
        </CardBody>
        <CardFooter justify="between">
          <Text size="small" color="text-weak">Already have an account?</Text>
          <Button as={Link} to="/login" label="Back to sign in" />
        </CardFooter>
      </Card>
    </Box>
  )
}

function LabeledInput({ label, value, onChange, type='text' }) {
  return (
    <Box gap="xxsmall">
      <Text size="small" weight={600}>{label}</Text>
      <TextInput type={type} value={value} onChange={e => onChange(e.target.value)} />
    </Box>
  )
}
