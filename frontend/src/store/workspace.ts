import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import { translate } from '../i18n'
import type { Lang, RunResult } from '../types'

export interface Project {
  id: string
  name: string
  createdAt: number
  updatedAt: number
}

export interface Session {
  id: string
  projectId: string
  title: string
  lang: Lang
  createdAt: number
  updatedAt: number
}

export type MessageRole = 'user' | 'assistant'
export type MessageStatus = 'running' | 'completed' | 'failed'

export interface Message {
  id: string
  sessionId: string
  role: MessageRole
  content: string
  status: MessageStatus
  result?: RunResult
  ticker?: string | null
  error?: string
  durationMs?: number
  createdAt: number
  updatedAt: number
}

export interface NewMessage {
  sessionId: string
  role: MessageRole
  content: string
  status: MessageStatus
  result?: RunResult
  ticker?: string | null
  error?: string
}

interface WorkspaceState {
  projects: Project[]
  sessions: Session[]
  messages: Message[]
  currentProjectId: string | null
  currentSessionId: string | null
  lang: Lang
  showThinking: boolean

  ensureDefaults: () => void
  createProject: () => { project: Project; session: Session }
  createSession: (projectId: string) => Session
  selectProject: (projectId: string) => string
  selectSession: (sessionId: string) => void
  setCurrent: (projectId: string, sessionId: string) => void
  addMessage: (msg: NewMessage) => string
  updateMessage: (id: string, patch: Partial<Omit<Message, 'id'>>) => void
  clearSession: (sessionId: string) => void
  setLang: (lang: Lang) => void
  setShowThinking: (v: boolean) => void
}

const uid = (): string =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2) + Date.now().toString(36)

const makeSession = (projectId: string, title: string, lang: Lang): Session => {
  const now = Date.now()
  return { id: uid(), projectId, title, lang, createdAt: now, updatedAt: now }
}

export const useWorkspace = create<WorkspaceState>()(
  persist(
    (set, get) => ({
      projects: [],
      sessions: [],
      messages: [],
      currentProjectId: null,
      currentSessionId: null,
      lang: 'zh',
      showThinking: false,

      ensureDefaults: () => {
        const s = get()
        if (s.projects.length === 0) {
          const now = Date.now()
          const project: Project = {
            id: uid(),
            name: translate(s.lang, 'defaultProjectName'),
            createdAt: now,
            updatedAt: now,
          }
          const session = makeSession(
            project.id,
            translate(s.lang, 'defaultSessionTitle'),
            s.lang,
          )
          set({
            projects: [project],
            sessions: [session],
            currentProjectId: project.id,
            currentSessionId: session.id,
          })
          return
        }

        let projectId = s.currentProjectId
        if (!projectId || !s.projects.some((p) => p.id === projectId)) {
          projectId = s.projects[0].id
        }
        const projSessions = s.sessions.filter((se) => se.projectId === projectId)
        let sessionId = s.currentSessionId
        if (!sessionId || !projSessions.some((se) => se.id === sessionId)) {
          if (projSessions.length > 0) {
            sessionId = projSessions[0].id
          } else {
            const session = makeSession(
              projectId,
              translate(s.lang, 'defaultSessionTitle'),
              s.lang,
            )
            set((state) => ({ sessions: [...state.sessions, session] }))
            sessionId = session.id
          }
        }
        set({ currentProjectId: projectId, currentSessionId: sessionId })
      },

      createProject: () => {
        const s = get()
        const now = Date.now()
        const project: Project = {
          id: uid(),
          name: `${translate(s.lang, 'defaultProjectName')} ${s.projects.length + 1}`,
          createdAt: now,
          updatedAt: now,
        }
        const session = makeSession(
          project.id,
          translate(s.lang, 'defaultSessionTitle'),
          s.lang,
        )
        set((state) => ({
          projects: [...state.projects, project],
          sessions: [...state.sessions, session],
          currentProjectId: project.id,
          currentSessionId: session.id,
        }))
        return { project, session }
      },

      createSession: (projectId) => {
        const s = get()
        const count = s.sessions.filter((se) => se.projectId === projectId).length
        const session = makeSession(
          projectId,
          `${translate(s.lang, 'defaultSessionTitle')} ${count + 1}`,
          s.lang,
        )
        set((state) => ({
          sessions: [...state.sessions, session],
          currentProjectId: projectId,
          currentSessionId: session.id,
        }))
        return session
      },

      selectProject: (projectId) => {
        const s = get()
        const projSessions = s.sessions
          .filter((se) => se.projectId === projectId)
          .sort((a, b) => b.updatedAt - a.updatedAt)
        if (projSessions.length > 0) {
          const sessionId = projSessions[0].id
          set({ currentProjectId: projectId, currentSessionId: sessionId })
          return sessionId
        }
        const session = makeSession(
          projectId,
          translate(s.lang, 'defaultSessionTitle'),
          s.lang,
        )
        set((state) => ({
          sessions: [...state.sessions, session],
          currentProjectId: projectId,
          currentSessionId: session.id,
        }))
        return session.id
      },

      selectSession: (sessionId) => {
        const session = get().sessions.find((se) => se.id === sessionId)
        if (!session) return
        set({ currentProjectId: session.projectId, currentSessionId: sessionId })
      },

      setCurrent: (projectId, sessionId) => {
        const s = get()
        const session = s.sessions.find(
          (se) => se.id === sessionId && se.projectId === projectId,
        )
        if (!session) return
        if (s.currentProjectId === projectId && s.currentSessionId === sessionId) {
          return
        }
        set({ currentProjectId: projectId, currentSessionId: sessionId })
      },

      addMessage: (msg) => {
        const now = Date.now()
        const message: Message = { id: uid(), createdAt: now, updatedAt: now, ...msg }
        set((state) => ({
          messages: [...state.messages, message],
          sessions: state.sessions.map((se) =>
            se.id === msg.sessionId ? { ...se, updatedAt: now } : se,
          ),
        }))
        return message.id
      },

      updateMessage: (id, patch) => {
        set((state) => ({
          messages: state.messages.map((m) =>
            m.id === id ? { ...m, ...patch, updatedAt: Date.now() } : m,
          ),
        }))
      },

      clearSession: (sessionId) => {
        set((state) => ({
          messages: state.messages.filter((m) => m.sessionId !== sessionId),
        }))
      },

      setLang: (lang) => {
        set((state) => ({
          lang,
          sessions: state.currentSessionId
            ? state.sessions.map((se) =>
                se.id === state.currentSessionId ? { ...se, lang } : se,
              )
            : state.sessions,
        }))
      },

      setShowThinking: (v) => set({ showThinking: v }),
    }),
    {
      name: 'fin-agent-workspace-v1',
      version: 1,
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        projects: state.projects,
        sessions: state.sessions,
        messages: state.messages,
        currentProjectId: state.currentProjectId,
        currentSessionId: state.currentSessionId,
        lang: state.lang,
        showThinking: state.showThinking,
      }),
      // On reload there is no in-flight fetch backing a persisted "running"
      // optimistic bubble, so it would otherwise hang forever and keep the
      // composer disabled. Demote any such stale message to a recoverable
      // failed state.
      onRehydrateStorage: () => (state) => {
        if (!state) return
        let changed = false
        const messages = state.messages.map((m) => {
          if (m.role === 'assistant' && m.status === 'running') {
            changed = true
            return {
              ...m,
              status: 'failed' as MessageStatus,
              error: '请求被刷新中断，请重试。 / Request was interrupted by a reload — please retry.',
            }
          }
          return m
        })
        if (changed) state.messages = messages
      },
    },
  ),
)
