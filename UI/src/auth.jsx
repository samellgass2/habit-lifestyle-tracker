import { createContext, useContext, useEffect, useState } from 'react'
import API from './api'
import { browserTimeZone } from './lib/tz'

// Identity is adamOS's: the gateway only serves this bundle to a signed-in
// session, and /api/habit-tracker/auth/me maps that person to a habits user.
// `reason` says why there is no user (e.g. "not_linked").

const AuthCtx = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loaded, setLoaded] = useState(false)
  const [reason, setReason] = useState(null)

  useEffect(() => {
    API.me()
      .then(data => {
        setUser(data.authenticated ? data.user : null)
        setReason(data.authenticated ? null : (data.reason || 'unauthenticated'))
        if (data.authenticated) API.setTimezone(browserTimeZone()).catch(() => {})
      })
      .catch(err => setReason(err?.data?.reason || 'unavailable'))
      .finally(() => setLoaded(true))
  }, [])

  const refreshAuth = async () => {
    const me = await API.me()
    setUser(me.user || null)
    return me
  }

  return (
    <AuthCtx.Provider value={{ user, loaded, reason, setUser, refreshAuth }}>
      {children}
    </AuthCtx.Provider>
  )
}

export function useAuth() {
  return useContext(AuthCtx)
}
