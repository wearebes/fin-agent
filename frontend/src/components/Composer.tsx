import { useState } from 'react'
import { ArrowUp, Workflow } from 'lucide-react'
import { translate } from '../i18n'
import type { Lang } from '../types'
import { useWorkspace } from '../store/workspace'

export default function Composer({
  lang,
  disabled,
  onSubmit,
}: {
  lang: Lang
  disabled: boolean
  onSubmit: (question: string, ticker: string | null) => void
}) {
  const [question, setQuestion] = useState('')
  const [ticker, setTicker] = useState('')
  const t = (k: string) => translate(lang, k)
  const showThinking = useWorkspace((s) => s.showThinking)
  const setShowThinking = useWorkspace((s) => s.setShowThinking)

  const submit = () => {
    const q = question.trim()
    if (!q || disabled) return
    onSubmit(q, ticker.trim() || null)
    setQuestion('')
    setTicker('')
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="composer">
      <div className="composer-card">
        <textarea
          className="composer-q"
          placeholder={t('phQ')}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={disabled}
          rows={3}
        />
        <div className="composer-row">
          <input
            className="composer-ticker"
            type="text"
            placeholder={t('phT')}
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            disabled={disabled}
          />
          <span className="composer-hint">{t('composerHint')}</span>

          <button
            type="button"
            className={`thinking-toggle${showThinking ? ' active' : ''}`}
            onClick={() => setShowThinking(!showThinking)}
            title={showThinking ? t('processOn') : t('processOff')}
            aria-pressed={showThinking}
          >
            <Workflow size={13} />
            <span className="thinking-toggle-label">{t('researchProcess')}</span>
          </button>

          <button
            className="send-btn"
            onClick={submit}
            disabled={disabled || !question.trim()}
          >
            {disabled ? <span className="spinner" /> : <ArrowUp size={15} />}
            <span>{disabled ? t('sending') : t('send')}</span>
          </button>
        </div>
      </div>
    </div>
  )
}
