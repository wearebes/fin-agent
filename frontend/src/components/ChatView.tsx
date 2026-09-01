import { useEffect, useMemo, useRef, useState } from 'react'
import { Eraser, PanelLeftClose, PanelLeftOpen, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { postResearchRun } from '../api/research'
import { getModelAccess } from '../api/models'
import type { ModelAccess } from '../api/models'
import { translate } from '../i18n'
import { recentResearch } from '../lib/research'
import type { ResearchMode, ResearchTurn } from '../types'
import { useWorkspace } from '../store/workspace'
import { useUserStore } from '../store/user'
import type { ModelSource } from '../store/user'
import Composer from './Composer'
import MessageBubble from './MessageBubble'
import ResearchExamples from './ResearchExamples'

export default function ChatView({ sidebarOpen, onToggleSidebar }: {
  sidebarOpen: boolean
  onToggleSidebar: () => void
}) {
  const modelSource = useUserStore((s) => s.modelSource)
  const setModelSource = useUserStore((s) => s.setModelSource)
  const user = useUserStore((s) => s.user)
  const [modelAccess, setModelAccess] = useState<ModelAccess>({
    local_codex: false, system_model: true, commercial_mode: false,
  })
  useEffect(() => {
    let active = true
    void getModelAccess().then((access) => {
      if (!active) return
      setModelAccess(access)
      if (!access.system_model && useUserStore.getState().modelSource === 'default') setModelSource('personal')
    }).catch(() => undefined)
    return () => { active = false }
  }, [user?.id, setModelSource])
  const lang = useWorkspace((s) => s.lang)
  const sessions = useWorkspace((s) => s.sessions)
  const allMessages = useWorkspace((s) => s.messages)
  const currentSessionId = useWorkspace((s) => s.currentSessionId)
  const addMessage = useWorkspace((s) => s.addMessage)
  const updateMessage = useWorkspace((s) => s.updateMessage)
  const updateSession = useWorkspace((s) => s.updateSession)
  const clearSession = useWorkspace((s) => s.clearSession)
  const planMode = useWorkspace((s) => s.planMode)
  const t = (k: string) => translate(lang, k)

  const session = sessions.find((se) => se.id === currentSessionId) ?? null

  const messages = useMemo(
    () =>
      allMessages
        .filter((m) => m.sessionId === currentSessionId)
        .sort((a, b) => a.createdAt - b.createdAt),
    [allMessages, currentSessionId],
  )

  const running = messages.some(
    (m) => m.role === 'assistant' && m.status === 'running',
  )

  const [useHistory, setUseHistory] = useState(true)
  const history = recentResearch(messages, currentSessionId)
  const draft = session?.draft ?? { question: '', ticker: '' }
  const updateDraft = (value: typeof draft) => {
    if (currentSessionId) updateSession(currentSessionId, { draft: value })
  }

  const scrollRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages.length, running])

  const submit = async (
    question: string,
    ticker: string | null,
    selectedSkill: string | null,
    mode?: ResearchMode,
    retryHistory?: ResearchTurn[],
  ) => {
    const state = useWorkspace.getState()
    if (!currentSessionId || state.messages.some((message) =>
      message.sessionId === currentSessionId && message.status === 'running',
    )) return
    const effectiveMode: ResearchMode = mode ?? (planMode ? 'plan' : 'auto')
    const inputHistory = retryHistory ?? (useHistory ? history : [])
    addMessage({
      sessionId: currentSessionId,
      role: 'user',
      content: question,
      status: 'completed',
      ticker,
      selectedSkill,
    })
    // Preserve the original input so retries do not pick up later conversation turns.
    const assistantId = addMessage({
      sessionId: currentSessionId,
      role: 'assistant',
      content: question,
      status: 'running',
      ticker,
      selectedSkill,
      history: inputHistory,
    })
    const startedAt = Date.now()
    try {
      const auth = useUserStore.getState()
      if (auth.modelSource !== 'default' && !auth.token) throw new Error('请登录后使用所选模型。 / Sign in first.')
      if (auth.modelSource === 'codex' && !modelAccess.local_codex) throw new Error('本机 Codex 不对当前账户开放。 / Local Codex is unavailable for this account.')
      const result = await postResearchRun(
        {
          question, ticker, lang, selectedSkill, mode: effectiveMode, history: inputHistory,
        },
        (progress) => updateMessage(assistantId, { progress }),
        auth.modelSource !== 'default' ? { token: auth.token!, source: auth.modelSource } : undefined,
      )
      updateMessage(assistantId, {
        status: result.status === 'failed' ? 'failed' : 'completed',
        result,
        durationMs: Date.now() - startedAt,
      })
    } catch (error) {
      updateMessage(assistantId, {
        status: 'failed',
        error: error instanceof Error ? error.message : String(error),
        durationMs: Date.now() - startedAt,
      })
    }
  }

  const onClear = () => {
    if (!currentSessionId || running) return
    if (window.confirm(t('clearConfirm'))) clearSession(currentSessionId)
  }

  const DEFAULT_SESSION_TITLES = [translate('zh', 'defaultSessionTitle'), translate('en', 'defaultSessionTitle')]
  const chatTitle = session?.title
    ? DEFAULT_SESSION_TITLES.includes(session.title) ? t('defaultSessionTitle') : session.title
    : ''

  return (
    <section className="chat">
      <header className="chat-header">
        <button type="button" className="sidebar-toggle" onClick={onToggleSidebar}
          aria-expanded={sidebarOpen} aria-controls="workspace-sidebar"
          aria-label={t(sidebarOpen ? 'hideProjectHistory' : 'showProjectHistory')}
          title={t(sidebarOpen ? 'hideProjectHistory' : 'showProjectHistory')}>
          {sidebarOpen ? <PanelLeftClose size={17} /> : <PanelLeftOpen size={17} />}
          <span>{t('projectHistory')}</span>
        </button>
        <span className="chat-title">{chatTitle}</span>
        {messages.length > 0 && (
          <button className="ghost-btn" onClick={onClear} disabled={running}>
            <Eraser size={14} />
            {t('clear')}
          </button>
        )}
      </header>

      <div className="messages" ref={scrollRef}>
        {messages.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">
              <Sparkles size={22} />
            </div>
            <h2 className="empty-title">{t('emptyTitle')}</h2>
            <p className="empty-desc">{t('emptyDesc')}</p>
            <ResearchExamples lang={lang} onSelect={updateDraft} />
          </div>
        ) : (
          <div className="messages-inner">
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} lang={lang} onRetry={submit}
                retryDisabled={running} />
            ))}
          </div>
        )}
      </div>

      <div className="research-model-select">
        <label>{lang === 'zh' ? '研究模型' : 'Research model'}<select value={modelSource} disabled={running} onChange={(event) => setModelSource(event.target.value as ModelSource)}>
          {modelAccess.system_model && <option value="default">{lang === 'zh' ? '系统默认' : 'System default'}</option>}
          <option value="personal" disabled={!user}>{lang === 'zh' ? '我的 API' : 'My API'}</option>
          {(modelAccess.local_codex || modelSource === 'codex') && <option value="codex" disabled={!modelAccess.local_codex}>
            {lang === 'zh' ? '本机 Codex · 个人额度' : 'Local Codex · personal quota'}
          </option>}
        </select></label>
        <Link to="/user/models">{lang === 'zh' ? '连接 / 管理 API' : 'Connect / manage API'}</Link>
      </div>
      <Composer lang={lang} disabled={running || !session} onSubmit={submit}
        draft={draft} onChange={updateDraft} hasHistory={history.length > 0}
        useHistory={useHistory} onHistoryChange={setUseHistory} />
    </section>
  )
}
