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
import EditHabit from './pages/EditHabit'
import Friends from './pages/Friends' 
import Inbox from './pages/Inbox.jsx'
import SendAction from './pages/SendAction.jsx'



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

        {/* AUTH / USER ROUTES */}
        <Route path="/login" element={<Login />} />
        <Route path="/create-account" element={<CreateAccount />} />

        {/* TOP LEVEL PAGE ROUTES */}
        <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
        <Route path="/reflect" element={<ProtectedRoute><Intake /></ProtectedRoute>} />
        <Route path="/track"   element={<ProtectedRoute><Track/></ProtectedRoute>} />
        <Route path="/rewards"   element={<ProtectedRoute><Rewards /></ProtectedRoute>} />
        <Route path="/account"   element={<ProtectedRoute><Me /></ProtectedRoute>} />
        <Route path="/inbox" element={<ProtectedRoute><Inbox /></ProtectedRoute>}/>

        {/* LOWER LEVEL REFLECT ROUTES */}
        <Route path="/reflect/daily" element={<ProtectedRoute><DayLog /></ProtectedRoute>} />

        {/* LOWER LEVEL TRACK ROUTES */}
        <Route path="/track/history" element={<ProtectedRoute><TrackHistory /></ProtectedRoute>} />
        <Route path="/track/create" element={<ProtectedRoute><TrackCreate /></ProtectedRoute>} />
        <Route path="/track/create/ai" element={<ProtectedRoute><TrackCreateAI /></ProtectedRoute>} />

        {/* LOWER LEVEL HABITS ROUTES */}
        <Route path="/habits/:id/edit" element={<ProtectedRoute><EditHabit /></ProtectedRoute>} />
        <Route path="/categories/new" element={<CreateCategory />} />
        <Route path="/habits/new" element={<CreateHabit />} />

        {/* LOWER LEVEL REWARDS ROUTES */}
        <Route path="/rewards/settings"   element={<ProtectedRoute><RewardSettings /></ProtectedRoute>} />
        <Route path="/rewards/history"   element={<ProtectedRoute><RewardHistory /></ProtectedRoute>} />

        {/* SOCIAL ROUTES */}
        <Route path="/account/friends" element={<ProtectedRoute><Friends /></ProtectedRoute>}/>
        <Route path="/send" element={<ProtectedRoute><SendAction /></ProtectedRoute>} />
        <Route path="/me/profile" element={<ProtectedRoute><UpdateProfile /></ProtectedRoute>} />

        {/* DEFAULT */}
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </>
    
  )
}
