import { useEffect, useState } from 'react'
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
import LocalSetupPage from './components/LocalSetupPage'
import LocalWorkspaceSync from './components/LocalWorkspaceSync'
import ResearchTasks from './components/ResearchTasks'
import ResearchJobSync from './components/ResearchJobSync'
import './research-tasks.css'
import { getLocalSetupStatus, type LocalSetupStatus } from './api/local'
import ModelSettingsPage from './components/user/ModelSettingsPage'
import { useWorkspace } from './store/workspace'

export default function App() {
  const ensureDefaults = useWorkspace((s) => s.ensureDefaults)
  const location = useLocation()
  const isQuant = location.pathname.startsWith('/quant')
  const isUser = location.pathname.startsWith('/user')
  const [setup, setSetup] = useState<LocalSetupStatus | null>(null)

  useEffect(() => {
    ensureDefaults()
  }, [ensureDefaults])

  useEffect(() => {
    void getLocalSetupStatus().then(setSetup).catch(() => {
      // Keep the existing app reachable if an older local backend is still starting.
      setSetup({ configured: true, workspace_persistent: false, auth_persistent: false })
    })
  }, [])

  if (!setup) return null
  if (!setup.configured) return <LocalSetupPage onComplete={() => setSetup({ ...setup, configured: true, auth_persistent: true })} />

  return (
    <div className={`app ${isQuant ? 'theme-dark' : 'theme-light'}`}>
      <LocalWorkspaceSync />
      <ResearchJobSync />
      <TopBar isQuant={isQuant} isUser={isUser} />
      <Routes>
        <Route path="/" element={<Navigate to="/chat" replace />} />
        <Route path="/chat" element={<ChatWorkspace />} />
        <Route path="/research/tasks" element={<ResearchTasks />} />
        <Route path="/research/tasks/:jobId" element={<ResearchTasks />} />
        <Route path="/p/:projectId/s/:sessionId" element={<ChatWorkspace />} />
        <Route path="/quant" element={<QuantView />} />
        <Route path="/user" element={<UserLayout />}>
          <Route index element={<Navigate to="/user/login" replace />} />
          <Route path="login" element={<LoginPage />} />
          <Route path="register" element={<RegisterPage />} />
          <Route path="profile" element={<ProfilePage />} />
          <Route path="password" element={<PasswordPage />} />
          <Route path="skills" element={<SkillsPage />} />
          <Route path="models" element={<ModelSettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/chat" replace />} />
      </Routes>
    </div>
  )
}
