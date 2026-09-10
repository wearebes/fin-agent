import { RotateCcw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { translate } from '../i18n'
import type { Lang, ResearchMode, ResearchTurn } from '../types'
import type { Message } from '../store/workspace'
import { useWorkspace } from '../store/workspace'
import AssistantResult from './AssistantResult'
import PlanApprovalPanel from './PlanApprovalPanel'
import ResearchProgress from './ResearchProgress'

export default function MessageBubble({
  message,
  lang,
  onRetry,
  retryDisabled = false,
}: {
  message: Message
  lang: Lang
  onRetry: (
    question: string,
    ticker: string | null,
    selectedSkill: string | null,
    mode?: ResearchMode,
    history?: ResearchTurn[],
  ) => void
  retryDisabled?: boolean
}) {
  const t = (k: string) => translate(lang, k)
  const showThinking = useWorkspace((s) => s.showThinking)
  const failed = message.status === 'failed' || message.result?.status === 'failed'

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
        {message.jobId && <Link className="research-job-link" to={`/research/tasks/${message.jobId}`}>
          {lang === 'zh' ? '查看后台研究任务与图文研报 →' : 'Open background task and illustrated report →'}</Link>}
        {message.status === 'running' && (
          <ResearchProgress progress={message.progress} startedAt={message.createdAt} lang={lang} background={!!message.jobClientId} />
        )}

        {failed && (
          <div className="failed-block">
            {!message.result && <div className="status-pill failed">
              <span className="status-dot" />
              {t('errorTitle')}
            </div>}
            {message.error && <p className="error-text">{message.error}</p>}
            <button
              className="retry-btn"
              disabled={retryDisabled}
              onClick={() => onRetry(message.content, message.ticker ?? null,
                message.selectedSkill ?? null, undefined,
                message.history ?? message.result?.request.history ?? [])}
            >
              <RotateCcw size={13} />
              {t('retry')}
            </button>
          </div>
        )}

        {message.status === 'completed' && message.result && message.result.status === 'awaiting_approval' && (
          <PlanApprovalPanel result={message.result} messageId={message.id} lang={lang} />
        )}
        {message.result && message.result.status !== 'awaiting_approval' && (
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
