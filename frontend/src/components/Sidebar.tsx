import { FolderPlus, MessageSquarePlus, Folder, MessageSquare } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { translate } from '../i18n'
import { useWorkspace } from '../store/workspace'

export default function Sidebar() {
  const navigate = useNavigate()
  const lang = useWorkspace((s) => s.lang)
  const projects = useWorkspace((s) => s.projects)
  const sessions = useWorkspace((s) => s.sessions)
  const currentProjectId = useWorkspace((s) => s.currentProjectId)
  const currentSessionId = useWorkspace((s) => s.currentSessionId)
  const createProject = useWorkspace((s) => s.createProject)
  const createSession = useWorkspace((s) => s.createSession)
  const selectProject = useWorkspace((s) => s.selectProject)
  const t = (k: string) => translate(lang, k)

  const onNewProject = () => {
    const { project, session } = createProject()
    navigate(`/p/${project.id}/s/${session.id}`)
  }

  const onSelectProject = (projectId: string) => {
    const sessionId = selectProject(projectId)
    navigate(`/p/${projectId}/s/${sessionId}`)
  }

  const onNewSession = (projectId: string) => {
    const session = createSession(projectId)
    navigate(`/p/${projectId}/s/${session.id}`)
  }

  const onSelectSession = (projectId: string, sessionId: string) => {
    navigate(`/p/${projectId}/s/${sessionId}`)
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-head">
        <span className="sidebar-title">{t('sbProjects')}</span>
        <button className="icon-btn" title={t('newProject')} onClick={onNewProject}>
          <FolderPlus size={16} />
        </button>
      </div>

      <div className="sidebar-list">
        {projects.map((project) => {
          const active = project.id === currentProjectId
          const projSessions = sessions
            .filter((se) => se.projectId === project.id)
            .sort((a, b) => b.updatedAt - a.updatedAt)
          return (
            <div className="project-group" key={project.id}>
              <button
                className={`project-row ${active ? 'active' : ''}`}
                onClick={() => onSelectProject(project.id)}
              >
                <Folder size={15} />
                <span className="row-label">{project.name}</span>
              </button>

              {active && (
                <div className="session-list">
                  {projSessions.map((session) => (
                    <button
                      key={session.id}
                      className={`session-row ${
                        session.id === currentSessionId ? 'active' : ''
                      }`}
                      onClick={() => onSelectSession(project.id, session.id)}
                    >
                      <MessageSquare size={14} />
                      <span className="row-label">{session.title}</span>
                    </button>
                  ))}
                  <button
                    className="session-row new"
                    onClick={() => onNewSession(project.id)}
                  >
                    <MessageSquarePlus size={14} />
                    <span className="row-label">{t('newSession')}</span>
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </aside>
  )
}
