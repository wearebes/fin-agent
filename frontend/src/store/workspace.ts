import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import { translate } from '../i18n'
import type { Lang, ResearchProgress, ResearchTurn, RunResult } from '../types'

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
  draft?: { question: string; ticker: string }
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
  selectedSkill?: string | null
  error?: string
  durationMs?: number
  history?: ResearchTurn[]
  progress?: ResearchProgress
  jobId?: string
  jobClientId?: string
  createdAt: number
  updatedAt: number
}

export type NewMessage = Omit<Message, 'id' | 'createdAt' | 'updatedAt' | 'durationMs'>

export interface WorkspaceSnapshot {
  projects: Project[]
  sessions: Session[]
  messages: Message[]
  currentProjectId: string | null
  currentSessionId: string | null
  lang: Lang
  showThinking: boolean
  planMode: boolean
}

interface WorkspaceState {
  projects: Project[]
  sessions: Session[]
  messages: Message[]
  currentProjectId: string | null
  currentSessionId: string | null
  lang: Lang
  showThinking: boolean
  planMode: boolean

  ensureDefaults: () => void
  createProject: () => { project: Project; session: Session }
  createSession: (projectId: string) => Session
  selectProject: (projectId: string) => string
  selectSession: (sessionId: string) => void
  setCurrent: (projectId: string, sessionId: string) => void
  addMessage: (msg: NewMessage) => string
  updateMessage: (id: string, patch: Partial<Omit<Message, 'id'>>) => void
  updateSession: (id: string, patch: Partial<Pick<Session, 'title' | 'draft'>>) => void
  clearSession: (sessionId: string) => void
  deleteProject: (projectId: string) => void
  deleteSession: (sessionId: string) => void
  setLang: (lang: Lang) => void
  setShowThinking: (v: boolean) => void
  setPlanMode: (v: boolean) => void
  replaceWorkspace: (snapshot: WorkspaceSnapshot) => void
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
      planMode: false,

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

        const projectId = (s.projects.find((p) => p.id === s.currentProjectId) ?? s.projects[0]).id
        const projSessions = s.sessions.filter((se) => se.projectId === projectId)
        const existing = projSessions.find((se) => se.id === s.currentSessionId) ?? projSessions[0]
        const session = existing ?? makeSession(
          projectId,
          translate(s.lang, 'defaultSessionTitle'),
          s.lang,
        )
        set({
          sessions: existing ? s.sessions : [...s.sessions, session],
          currentProjectId: projectId,
          currentSessionId: session.id,
        })
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
        const existing = s.sessions
          .filter((se) => se.projectId === projectId)
          .sort((a, b) => b.updatedAt - a.updatedAt)[0]
        const session = existing ?? makeSession(
          projectId,
          translate(s.lang, 'defaultSessionTitle'),
          s.lang,
        )
        set({
          sessions: existing ? s.sessions : [...s.sessions, session],
          currentProjectId: projectId,
          currentSessionId: session.id,
        })
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
        const firstQuestion = msg.role === 'user' && !get().messages.some(
          (item) => item.sessionId === msg.sessionId && item.role === 'user',
        )
        set((state) => ({
          messages: [...state.messages, message],
          sessions: state.sessions.map((se) =>
            se.id === msg.sessionId ? {
              ...se, updatedAt: now,
              title: firstQuestion ? msg.content.replace(/\s+/g, ' ').trim().slice(0, 48) : se.title,
            } : se,
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

      updateSession: (id, patch) => set((state) => ({
        sessions: state.sessions.map((session) =>
          session.id === id ? { ...session, ...patch } : session,
        ),
      })),

      deleteProject: (projectId) => {
        const s = get()
        const sessionIds = new Set(
          s.sessions.filter((se) => se.projectId === projectId).map((se) => se.id),
        )
        set((state) => ({
          projects: state.projects.filter((p) => p.id !== projectId),
          sessions: state.sessions.filter((se) => se.projectId !== projectId),
          messages: state.messages.filter((m) => !sessionIds.has(m.sessionId)),
          currentProjectId:
            state.currentProjectId === projectId
              ? state.projects.find((p) => p.id !== projectId)?.id ?? null
              : state.currentProjectId,
          currentSessionId:
            sessionIds.has(state.currentSessionId ?? '')
              ? null
              : state.currentSessionId,
        }))
      },

      deleteSession: (sessionId) => {
        set((state) => ({
          sessions: state.sessions.filter((se) => se.id !== sessionId),
          messages: state.messages.filter((m) => m.sessionId !== sessionId),
          currentSessionId:
            state.currentSessionId === sessionId ? null : state.currentSessionId,
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
      setPlanMode: (v) => set({ planMode: v }),
      replaceWorkspace: (snapshot) => set({
        projects: Array.isArray(snapshot.projects) ? snapshot.projects : [],
        sessions: Array.isArray(snapshot.sessions) ? snapshot.sessions : [],
        messages: Array.isArray(snapshot.messages) ? snapshot.messages : [],
        currentProjectId: snapshot.currentProjectId ?? null,
        currentSessionId: snapshot.currentSessionId ?? null,
        lang: snapshot.lang === 'en' ? 'en' : 'zh',
        showThinking: Boolean(snapshot.showThinking),
        planMode: Boolean(snapshot.planMode),
      }),
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
        planMode: state.planMode,
      }),
      // A reload cancels requests; stale running messages must not lock the composer.
      onRehydrateStorage: () => (state) => {
        if (!state) return
        for (const message of state.messages) {
          if (message.role !== 'assistant' || message.status !== 'running') continue
          if (message.jobClientId) continue
          message.status = 'failed'
          message.error = '请求被刷新中断，请重试。 / Request was interrupted by a reload — please retry.'
        }
      },
    },
  ),
)
