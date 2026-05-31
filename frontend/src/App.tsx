import { useEffect } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import TopBar from './components/TopBar'
import ChatWorkspace from './components/ChatWorkspace'
import QuantView from './components/QuantView'
import { useWorkspace } from './store/workspace'

export default function App() {
  const ensureDefaults = useWorkspace((s) => s.ensureDefaults)
  const location = useLocation()
  const isQuant = location.pathname.startsWith('/quant')

  useEffect(() => {
    ensureDefaults()
  }, [ensureDefaults])

  return (
    <div className={`app ${isQuant ? 'theme-dark' : 'theme-light'}`}>
      <TopBar isQuant={isQuant} />
      <Routes>
        <Route path="/" element={<Navigate to="/chat" replace />} />
        <Route path="/chat" element={<ChatWorkspace />} />
        <Route path="/p/:projectId/s/:sessionId" element={<ChatWorkspace />} />
        <Route path="/quant" element={<QuantView />} />
        <Route path="*" element={<Navigate to="/chat" replace />} />
      </Routes>
    </div>
  )
}
