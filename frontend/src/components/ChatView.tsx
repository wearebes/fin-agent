import { useEffect, useMemo, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Eraser, Sparkles } from 'lucide-react'
import { postResearchRun } from '../api/research'
import { translate } from '../i18n'
import { useWorkspace } from '../store/workspace'
import Composer from './Composer'
import MessageBubble from './MessageBubble'

export default function ChatView() {
  const lang = useWorkspace((s) => s.lang)
  const sessions = useWorkspace((s) => s.sessions)
  const allMessages = useWorkspace((s) => s.messages)
  const currentSessionId = useWorkspace((s) => s.currentSessionId)
  const addMessage = useWorkspace((s) => s.addMessage)
  const updateMessage = useWorkspace((s) => s.updateMessage)
  const clearSession = useWorkspace((s) => s.clearSession)
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

  const mutation = useMutation({ mutationFn: postResearchRun })

  const scrollRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages.length, running])

  const submit = (question: string, ticker: string | null) => {
    if (!currentSessionId || running) return
    addMessage({
      sessionId: currentSessionId,
      role: 'user',
      content: question,
      status: 'completed',
      ticker,
    })
    // Optimistic "running" assistant bubble. `content` carries the question so a
    // failed bubble can be retried without scanning neighbours.
    const assistantId = addMessage({
      sessionId: currentSessionId,
      role: 'assistant',
      content: question,
      status: 'running',
      ticker,
    })
    const startedAt = Date.now()
    mutation.mutate(
      { question, ticker, lang },
      {
        onSuccess: (result) =>
          updateMessage(assistantId, {
            status: 'completed',
            result,
            durationMs: Date.now() - startedAt,
          }),
        onError: (error) =>
          updateMessage(assistantId, {
            status: 'failed',
            error: error instanceof Error ? error.message : String(error),
            durationMs: Date.now() - startedAt,
          }),
      },
    )
  }

  const onClear = () => {
    if (!currentSessionId || running) return
    if (window.confirm(t('clearConfirm'))) clearSession(currentSessionId)
  }

  return (
    <section className="chat">
      <header className="chat-header">
        <span className="chat-title">{session?.title ?? ''}</span>
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
          </div>
        ) : (
          <div className="messages-inner">
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} lang={lang} onRetry={submit} />
            ))}
          </div>
        )}
      </div>

      <Composer lang={lang} disabled={running} onSubmit={submit} />
    </section>
  )
}
