import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { Grommet } from 'grommet'
import { computeTheme } from './theme/dynamicTheme'
import App from './App.jsx'
import { AuthProvider } from './auth.jsx'
import useDynamicTheme from './theme/useDynamicTheme'

const { theme, mode } = computeTheme()

function ThemedApp() {
  const theme = useDynamicTheme()
  return (
    <Grommet theme={theme} themeMode={mode} full>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </Grommet>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(<ThemedApp />)
