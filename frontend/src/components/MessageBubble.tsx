import { RotateCcw } from 'lucide-react'
import { translate } from '../i18n'
import type { Lang } from '../types'
import type { Message } from '../store/workspace'
import { useWorkspace } from '../store/workspace'
import AssistantResult from './AssistantResult'
import PlanApprovalPanel from './PlanApprovalPanel'

export default function MessageBubble({
  message,
  lang,
  onRetry,
}: {
  message: Message
  lang: Lang
  onRetry: (question: string, ticker: string | null, selectedSkill: string | null) => void
}) {
  const t = (k: string) => translate(lang, k)
  const showThinking = useWorkspace((s) => s.showThinking)

  if (message.role === 'user') {
    return (
      <div className="msg user">
        <div className="bubble user-bubble">
          <div className="bubble-text">{message.content}</div>
          {(message.ticker || message.selectedSkill) && (
            <div className="bubble-chips">
              {message.selectedSkill && (
                <span className="skill-chip">/{message.selectedSkill}</span>
              )}
              {message.ticker && <span className="ticker-chip">{message.ticker}</span>}
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="msg assistant">
      <div className="bubble assistant-bubble">
        {message.status === 'running' && (
          <div className="status-pill running">
            <span className="spinner" />
            {t('running')}
          </div>
        )}

        {message.status === 'failed' && (
          <div className="failed-block">
            <div className="status-pill failed">
              <span className="status-dot" />
              {t('errorTitle')}
            </div>
            {message.error && <p className="error-text">{message.error}</p>}
            <button
              className="retry-btn"
              onClick={() =>
                onRetry(message.content, message.ticker ?? null, message.selectedSkill ?? null)
              }
            >
              <RotateCcw size={13} />
              {t('retry')}
            </button>
          </div>
        )}

        {message.status === 'completed' && message.result && message.result.status === 'awaiting_approval' && (
          <PlanApprovalPanel result={message.result} messageId={message.id} lang={lang} />
        )}
        {message.status === 'completed' && message.result && message.result.status !== 'awaiting_approval' && (
          <AssistantResult
            result={message.result}
            lang={lang}
            durationMs={message.durationMs}
            defaultThinkingOpen={showThinking}
          />
        )}
      </div>
    </div>
  )
}
