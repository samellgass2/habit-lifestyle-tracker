import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { Grommet } from 'grommet'
import App from './App.jsx'
import { AuthProvider } from './auth.jsx'
import useDynamicTheme from './theme/useDynamicTheme'

function ThemedApp() {
  const theme = useDynamicTheme()
  return (
    <Grommet full theme={theme} themeMode={theme.global?.colors?.background?.includes(' 7%)') ? 'dark' : 'light'}>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </Grommet>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(<ThemedApp />)
