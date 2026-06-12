import { useEffect } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import TopBar from './components/TopBar'
import ChatWorkspace from './components/ChatWorkspace'
import QuantView from './components/QuantView'
import UserLayout from './components/user/UserLayout'
import LoginPage from './components/user/LoginPage'
import RegisterPage from './components/user/RegisterPage'
import ProfilePage from './components/user/ProfilePage'
import PasswordPage from './components/user/PasswordPage'
import SkillsPage from './components/user/SkillsPage'
import { useWorkspace } from './store/workspace'

export default function App() {
  const ensureDefaults = useWorkspace((s) => s.ensureDefaults)
  const location = useLocation()
  const isQuant = location.pathname.startsWith('/quant')
  const isUser = location.pathname.startsWith('/user')

  useEffect(() => {
    ensureDefaults()
  }, [ensureDefaults])

  return (
    <div className={`app ${isQuant ? 'theme-dark' : 'theme-light'}`}>
      <TopBar isQuant={isQuant} isUser={isUser} />
      <Routes>
        <Route path="/" element={<Navigate to="/chat" replace />} />
        <Route path="/chat" element={<ChatWorkspace />} />
        <Route path="/p/:projectId/s/:sessionId" element={<ChatWorkspace />} />
        <Route path="/quant" element={<QuantView />} />
        <Route path="/user" element={<UserLayout />}>
          <Route index element={<Navigate to="/user/login" replace />} />
          <Route path="login" element={<LoginPage />} />
          <Route path="register" element={<RegisterPage />} />
          <Route path="profile" element={<ProfilePage />} />
          <Route path="password" element={<PasswordPage />} />
          <Route path="skills" element={<SkillsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/chat" replace />} />
      </Routes>
    </div>
  )
}
