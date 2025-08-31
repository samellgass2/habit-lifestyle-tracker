import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth'

export default function ProtectedRoute({ children }) {
  const { user, loaded } = useAuth()
  const loc = useLocation()

  if (!loaded) return null // or a spinner

  if (!user) {
    // redirect to login, remember where we wanted to go
    return <Navigate to="/login" state={{ from: loc }} replace />
  }

  return children
}
