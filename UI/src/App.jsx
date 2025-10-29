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
import Track from './pages/Track'
import CreateCategory from './pages/CreateCategory'
import CreateHabit from './pages/CreateHabit'
import Rewards from './pages/Rewards'
import RewardSettings from './pages/RewardSettings'
import RewardHistory from './pages/RewardHistory'
import TrackHistory from './pages/TrackHistory'
import TrackCreate from './pages/TrackCreate'
import TrackCreateAI from './pages/TrackCreateAI'


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
        <Route path="/track"   element={<ProtectedRoute><Track/></ProtectedRoute>} />
        <Route path="/track/history" element={<ProtectedRoute><TrackHistory /></ProtectedRoute>} />
        <Route path="/track/create" element={<ProtectedRoute><TrackCreate /></ProtectedRoute>} />
        <Route path="/track/create/ai" element={<ProtectedRoute><TrackCreateAI /></ProtectedRoute>} />
        <Route path="/rewards"   element={<ProtectedRoute><Rewards /></ProtectedRoute>} />
        <Route path="/rewards/settings"   element={<ProtectedRoute><RewardSettings /></ProtectedRoute>} />
        <Route path="/rewards/history"   element={<ProtectedRoute><RewardHistory /></ProtectedRoute>} />

        <Route path="/account"   element={<Me />} />
        <Route path="/create-account" element={<CreateAccount />} />
        <Route path="/reflect" element={<ProtectedRoute><Intake /></ProtectedRoute>} />
        <Route path="/reflect/daily" element={<ProtectedRoute><DayLog /></ProtectedRoute>} />
        <Route path="/intake/activity" element={<ProtectedRoute><Stub title="Activity Intake" /></ProtectedRoute>} />
        <Route path="/me/profile" element={<UpdateProfile />} />
        <Route path="/categories/new" element={<CreateCategory />} />
        <Route path="/habits/new" element={<CreateHabit />} />

        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </>
    
  )
}
