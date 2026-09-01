import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import Sidebar from './Sidebar'
import ChatView from './ChatView'
import { useWorkspace } from '../store/workspace'

export default function ChatWorkspace() {
  const { projectId, sessionId } = useParams()
  const setCurrent = useWorkspace((s) => s.setCurrent)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  // Sync a deep-linked /p/:projectId/s/:sessionId into the store. Invalid ids
  // are ignored (setCurrent validates existence), keeping the defaults.
  useEffect(() => {
    if (projectId && sessionId) {
      setCurrent(projectId, sessionId)
      setSidebarOpen(false)
    }
  }, [projectId, sessionId, setCurrent])

  return (
    <div className="workspace">
      <Sidebar hidden={!sidebarOpen} />
      <ChatView sidebarOpen={sidebarOpen} onToggleSidebar={() => setSidebarOpen((open) => !open)} />
    </div>
  )
}
