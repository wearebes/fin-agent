import { useState } from 'react'
import { ChevronDown, Workflow } from 'lucide-react'
import { translate } from '../i18n'
import type { Lang, TraceRecord } from '../types'

export default function ResearchProcessPanel({
  trace,
  plannedStages,
  durationMs,
  defaultOpen,
  lang,
}: {
  trace: TraceRecord[]
  plannedStages: string[]
  durationMs?: number
  defaultOpen: boolean
  lang: Lang
}) {
  const [open, setOpen] = useState(defaultOpen)
  const t = (k: string) => translate(lang, k)

  if (trace.length === 0 && plannedStages.length === 0) return null

  const durationLabel =
    durationMs != null
      ? durationMs < 1000
        ? `${durationMs}ms`
        : `${(durationMs / 1000).toFixed(1)}s`
      : null

  return (
    <div className="thinking-panel">
      <button
        type="button"
        className="thinking-head"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <Workflow size={13} className="thinking-icon" />
        <span className="thinking-title">{t('researchProcess')}</span>
        {durationLabel && (
          <span className="thinking-duration">
            {t('duration')} {durationLabel}
          </span>
        )}
        <ChevronDown
          size={13}
          className={`thinking-chevron${open ? ' open' : ''}`}
        />
      </button>

      {open && (
        <div className="thinking-body">
          {plannedStages.length > 0 && (
            <div className="thinking-stages">
              {plannedStages.map((s, i) => (
                <span className="meta-chip" key={`${s}-${i}`}>
                  {s}
                </span>
              ))}
            </div>
          )}

          {trace.length > 0 && (
            <div className="trace-timeline">
              {trace.map((tr, i) => (
                <div className="trace-node" key={i}>
                  <div className="trace-stage">{tr.stage}</div>
                  <div className="trace-detail">{tr.detail}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
