import { createContext, useContext, useEffect, useState } from 'react'
import API from './api'
import { browserTimeZone } from './lib/tz'

const AuthCtx = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    // hydrate auth state on app start
    API.me().then(data => {
      setUser(data.authenticated ? data.user : null)
      setLoaded(true)
    }).catch(() => setLoaded(true))
  }, [])

  async function login(username, password) {
    await API.login(username, password)
    // fetch user (so we have id/username in context)
    const me = await API.me()
    setUser(me.user)

    // fire-and-forget: tell backend our IANA tz
    try {
      await API.setTimezone(browserTimeZone())
    } catch { /* non-fatal */ }

    return me
  }

  const logout = async () => {
    await API.logout()
    setUser(null)
  }

  return (
    <AuthCtx.Provider value={{ user, loaded, login, logout }}>
      {children}
    </AuthCtx.Provider>
  )
}

export function useAuth() {
  return useContext(AuthCtx)
}
