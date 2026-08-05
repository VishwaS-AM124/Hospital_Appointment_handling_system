import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'

import { setUnauthorizedHandler, tokenStore } from '../api/client'
import * as endpoints from '../api/endpoints'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  // `loading` guards the first paint: without it, a page-refresh on a protected route
  // would bounce to /login before the stored token has been validated.
  const [loading, setLoading] = useState(true)

  const logout = useCallback(() => {
    tokenStore.clear()
    setUser(null)
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null))
    return () => setUnauthorizedHandler(null)
  }, [])

  useEffect(() => {
    let cancelled = false

    async function restoreSession() {
      if (!tokenStore.get()) {
        setLoading(false)
        return
      }
      try {
        // Re-validate against the server rather than trusting the cached token: it may
        // have expired, or the account may be gone.
        const me = await endpoints.fetchMe()
        if (!cancelled) setUser(me)
      } catch {
        tokenStore.clear()
        if (!cancelled) setUser(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    restoreSession()
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (email, password) => {
    const session = await endpoints.login(email, password)
    tokenStore.set(session.access_token)
    setUser(session.user)
    return session.user
  }, [])

  const register = useCallback(
    async (payload) => {
      await endpoints.register(payload)
      return login(payload.email, payload.password)
    },
    [login],
  )

  const value = useMemo(
    () => ({
      user,
      loading,
      login,
      register,
      logout,
      isDoctor: user?.role === 'DOCTOR',
      isPatient: user?.role === 'PATIENT',
      homePath: user?.role === 'DOCTOR' ? '/doctor' : '/patient',
    }),
    [user, loading, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}
