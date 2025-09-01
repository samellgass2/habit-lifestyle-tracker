import { Routes, Route, Navigate } from 'react-router-dom'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import ProtectedRoute from './components/ProtectedRoute'
import BottomNav from './components/BottomNav'
import EnvBanner from './components/EnvBanner'
import CreateAccount from './pages/CreateAccount'
import Intake from './pages/Intake'
import DayLog from './pages/DayLog'
import UpdateProfile from './pages/UpdateProfile'
import Me from './pages/Me'


const Stub = ({ title }) => (
  <div style={{ padding: 16, paddingBottom: 80 }}>
    <h3>{title}</h3>
    <p>This page is under construction!🗣️🗣️🫃🏻</p>
    <BottomNav />
  </div>
)

export default function App() {
  return (
    <>
      <EnvBanner />
        <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
        <Route path="/reflect"   element={<ProtectedRoute><Stub title="Reflection" /></ProtectedRoute>} />
        <Route path="/rewards"   element={<ProtectedRoute><Stub title="Rewards" /></ProtectedRoute>} />
        <Route path="/account"   element={<Me />} />
        <Route path="/create-account" element={<CreateAccount />} />
        <Route path="/intake" element={<ProtectedRoute><Intake /></ProtectedRoute>} />
        <Route path="/intake/daily" element={<ProtectedRoute><DayLog /></ProtectedRoute>} />
        <Route path="/intake/activity" element={<ProtectedRoute><Stub title="Activity Intake" /></ProtectedRoute>} />
        <Route path="/me/profile" element={<UpdateProfile />} />


        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </>
    
  )
}
