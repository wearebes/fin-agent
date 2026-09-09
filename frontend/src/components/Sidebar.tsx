import { useState } from 'react'
import { FolderPlus, MessageSquarePlus, Folder, MessageSquare, Trash2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { translate } from '../i18n'
import { useWorkspace } from '../store/workspace'

export default function Sidebar({ hidden = false }: { hidden?: boolean }) {
  const navigate = useNavigate()
  const lang = useWorkspace((s) => s.lang)
  const projects = useWorkspace((s) => s.projects)
  const sessions = useWorkspace((s) => s.sessions)
  const messages = useWorkspace((s) => s.messages)
  const [query, setQuery] = useState('')
  const currentProjectId = useWorkspace((s) => s.currentProjectId)
  const currentSessionId = useWorkspace((s) => s.currentSessionId)
  const createProject = useWorkspace((s) => s.createProject)
  const createSession = useWorkspace((s) => s.createSession)
  const selectProject = useWorkspace((s) => s.selectProject)
  const deleteProject = useWorkspace((s) => s.deleteProject)
  const deleteSession = useWorkspace((s) => s.deleteSession)
  const t = (k: string) => translate(lang, k)
  const search = query.trim().toLocaleLowerCase()
  const matches = (value: string) => value.toLocaleLowerCase().includes(search)
  const runningSessions = new Set(messages.filter((message) => message.status === 'running')
    .map((message) => message.sessionId))

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
  const visibleProjects = projects.filter((project) => matches(displayName(project.name)) ||
    sessions.some((session) => session.projectId === project.id && matches(displayTitle(session.title))),
  )

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
    if (type === 'session' ? runningSessions.has(id) : sessions.some(
      (session) => session.projectId === id && runningSessions.has(session.id),
    )) return
    if (confirmTarget && confirmTarget.type === type && confirmTarget.id === id) {
      if (type === 'project') {
        deleteProject(id)
      } else {
        deleteSession(id)
      }
      useWorkspace.getState().ensureDefaults()
      const state = useWorkspace.getState()
      navigate(`/p/${state.currentProjectId}/s/${state.currentSessionId}`)
      setConfirmTarget(null)
    } else {
      setConfirmTarget({ type, id })
      setTimeout(() => setConfirmTarget(null), 3000)
    }
  }

  return (
    <aside className="sidebar" id="workspace-sidebar" hidden={hidden} aria-label={t('projectHistory')}>
      <div className="sidebar-head">
        <span className="sidebar-title">{t('sbProjects')}</span>
        <button className="icon-btn" title={t('newProject')} onClick={onNewProject}>
          <FolderPlus size={16} />
        </button>
      </div>

      <input className="session-search" type="search" value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder={t('searchSessions')} aria-label={t('searchSessions')} />

      <div className="sidebar-list">
        {visibleProjects.length === 0 && <p className="source-note">{t('noSessions')}</p>}
        {visibleProjects.map((project) => {
          const active = project.id === currentProjectId
          const projSessions = sessions
            .filter((se) => se.projectId === project.id)
            .filter((se) => !search || matches(displayName(project.name)) || matches(displayTitle(se.title)))
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
                  disabled={sessions.some((se) => se.projectId === project.id && runningSessions.has(se.id))}
                  onClick={(e) => { e.stopPropagation(); handleDelete('project', project.id) }}
                >
                  <Trash2 size={13} />
                </button>
              </div>

              {(active || search) && (
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
                          disabled={runningSessions.has(session.id)}
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
