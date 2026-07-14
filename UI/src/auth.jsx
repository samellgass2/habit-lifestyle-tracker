import { createContext, useContext, useEffect, useState } from 'react'
import API from './api'
import { browserTimeZone } from './lib/tz'

const AuthCtx = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    API.me()
      .then(data => { setUser(data.authenticated ? data.user : null) })
      .finally(() => setLoaded(true))
  }, [])

  async function login(username, password) {
    await API.login(username, password)
    const me = await API.me()             // /api/auth/me now includes emoji/color
    setUser(me.user)

    // fire-and-forget timezone
    API.setTimezone(browserTimeZone()).catch(() => {})

    return me
  }

  const logout = async () => {
    await API.logout()
    setUser(null)
  }

  const refreshAuth = async () => {
    const me = await API.me()
    setUser(me.user || null)
    return me
  }

  return (
    <AuthCtx.Provider value={{ user, loaded, login, logout, setUser, refreshAuth }}>
      {children}
    </AuthCtx.Provider>
  )
}

export function useAuth() {
  return useContext(AuthCtx)
}
