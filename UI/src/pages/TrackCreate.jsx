import { Box, Button, Heading, Text } from 'grommet'
import { FormPreviousLink, Magic } from 'grommet-icons'
import { useNavigate } from 'react-router-dom'
import BottomNav from '../components/BottomNav'

export default function TrackCreate() {
  const nav = useNavigate()
  return (
    <Box fill>
      <Box pad={{ horizontal: 'medium', top: 'small' }} gap="medium">
        <Box height="30px" />
        <Box direction="row" justify="between" align="center">
          <Heading level={3} margin="none">Create</Heading>
          <Button icon={<FormPreviousLink size="large" />} onClick={() => nav('/track')} plain pad="xsmall" />
        </Box>

        <Text color="text-weak">Pick a way to add a new habit.</Text>

        <Box direction="row" wrap gap="small" margin={{ top: 'small' }}>
          <Box basis="1/2" flex>
            <Button
              primary
              fill="horizontal"
              size="large"
              label="Create Category"
              onClick={() => nav('/categories/new')}
            />
          </Box>
          <Box basis="1/2" flex pad={{ top: 'small' }}>
            <Button
              fill="horizontal"
              size="large"
              label="Add Habit"
              onClick={() => nav('/habits/new')}
            />
          </Box>
          <Box basis="full" pad={{ top: 'small' }}>
            <Button
              icon={<Magic />}
              primary
              fill="horizontal"
              size="large"
              label="Create with AI"
              onClick={() => nav('/track/create/ai')}
            />
          </Box>
          <Box height="250px" />
        </Box>
      </Box>
      <BottomNav />
    </Box>
  )
}
