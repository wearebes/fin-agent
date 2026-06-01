import { useState } from 'react'
import { FolderPlus, MessageSquarePlus, Folder, MessageSquare, Trash2 } from 'lucide-react'
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
  const deleteProject = useWorkspace((s) => s.deleteProject)
  const deleteSession = useWorkspace((s) => s.deleteSession)
  const t = (k: string) => translate(lang, k)

  const DEFAULT_PROJECT_NAMES = [translate('zh', 'defaultProjectName'), translate('en', 'defaultProjectName')]
  const DEFAULT_SESSION_TITLES = [translate('zh', 'defaultSessionTitle'), translate('en', 'defaultSessionTitle')]

  const displayName = (name: string) => {
    if (DEFAULT_PROJECT_NAMES.includes(name)) return t('defaultProjectName')
    return name
  }
  const displayTitle = (title: string) => {
    if (DEFAULT_SESSION_TITLES.includes(title)) return t('defaultSessionTitle')
    return title
  }

  const [confirmTarget, setConfirmTarget] = useState<{ type: 'project' | 'session'; id: string } | null>(null)

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

  const handleDelete = (type: 'project' | 'session', id: string) => {
    if (confirmTarget && confirmTarget.type === type && confirmTarget.id === id) {
      if (type === 'project') {
        deleteProject(id)
        const remaining = projects.filter((p) => p.id !== id)
        if (remaining.length > 0) {
          const sid = selectProject(remaining[0].id)
          navigate(`/p/${remaining[0].id}/s/${sid}`)
        } else {
          navigate('/chat')
        }
      } else {
        deleteSession(id)
      }
      setConfirmTarget(null)
    } else {
      setConfirmTarget({ type, id })
      setTimeout(() => setConfirmTarget(null), 3000)
    }
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
          const isConfirmingProject = confirmTarget?.type === 'project' && confirmTarget?.id === project.id
          return (
            <div className="project-group" key={project.id}>
              <div className={`project-row-wrapper ${active ? 'active' : ''}`}>
                <button
                  className="project-row"
                  onClick={() => onSelectProject(project.id)}
                >
                  <Folder size={15} />
                  <span className="row-label">{displayName(project.name)}</span>
                </button>
                <button
                  className={`delete-btn ${isConfirmingProject ? 'confirming' : ''}`}
                  title={isConfirmingProject ? t('confirmDelete') : t('deleteProject')}
                  onClick={(e) => { e.stopPropagation(); handleDelete('project', project.id) }}
                >
                  <Trash2 size={13} />
                </button>
              </div>

              {active && (
                <div className="session-list">
                  {projSessions.map((session) => {
                    const isConfirmingSession = confirmTarget?.type === 'session' && confirmTarget?.id === session.id
                    return (
                      <div className={`session-row-wrapper ${session.id === currentSessionId ? 'active' : ''}`} key={session.id}>
                        <button
                          className="session-row"
                          onClick={() => onSelectSession(project.id, session.id)}
                        >
                          <MessageSquare size={14} />
                          <span className="row-label">{displayTitle(session.title)}</span>
                        </button>
                        <button
                          className={`delete-btn ${isConfirmingSession ? 'confirming' : ''}`}
                          title={isConfirmingSession ? t('confirmDelete') : t('deleteSession')}
                          onClick={(e) => { e.stopPropagation(); handleDelete('session', session.id) }}
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    )
                  })}
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
