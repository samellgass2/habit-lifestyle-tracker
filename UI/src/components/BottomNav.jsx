import { useLocation, useNavigate } from 'react-router-dom'
import { Box, Button, Text } from 'grommet'
import { Home, Clipboard, Edit, Trophy, User } from 'grommet-icons'

const tabs = [
  { path: '/dashboard', label: 'Home', icon: Home },
  { path: '/intake',    label: 'Track', icon: Clipboard },
  { path: '/reflect',   label: 'Reflect', icon: Edit },
  { path: '/rewards',   label: 'Rewards', icon: Trophy },
  { path: '/account',   label: 'Me', icon: User },
]

export default function BottomNav() {
  const nav = useNavigate()
  const loc = useLocation()

  return (
    <Box
      as="nav"
      direction="row"
      justify="between"
      align="center"
      gap="small"
      pad={{ horizontal: 'medium', vertical: 'xsmall' }}
      background="background"
      border={{ side: 'top', color: 'border' }}
      style={{
        position: 'fixed',
        bottom: 0, left: 0, right: 0,
        backdropFilter: 'blur(8px)'
      }}
    >
      {tabs.map(({ path, label, icon: Icon }) => {
        const active = loc.pathname.startsWith(path)
        return (
          <Button key={path} plain onClick={() => nav(path)}>
            <Box align="center" gap="xxsmall" pad="xsmall" round="small"
                 background={active ? 'accent-1' : undefined}>
              <Icon color={active ? 'background' : 'text'} />
              <Text size="xsmall" color={active ? 'background' : 'text-weak'}>{label}</Text>
            </Box>
          </Button>
        )
      })}
    </Box>
  )
}
