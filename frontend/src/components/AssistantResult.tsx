import { translate } from '../i18n'
import type { Lang, RunResult, RunStatus } from '../types'
import Markdown from './Markdown'
import ResearchProcessPanel from './ResearchProcessPanel'

const pillClass = (status: RunStatus): string => {
  if (status === 'completed') return 'completed'
  if (status === 'failed') return 'failed'
  return 'running'
}

export default function AssistantResult({
  result,
  lang,
  durationMs,
  defaultThinkingOpen,
}: {
  result: RunResult
  lang: Lang
  durationMs?: number
  defaultThinkingOpen: boolean
}) {
  const t = (k: string) => translate(lang, k)

  return (
    <div className="result">
      <div className={`status-pill ${pillClass(result.status)}`}>
        <span className="status-dot" />
        {t(result.status)}
      </div>

      <div className="meta-row">
        <span className="meta-chip">
          <strong>{t('runId')}</strong> {result.run_id}
        </span>
        {result.environment && (
          <span className="meta-chip">
            <strong>{t('env')}</strong> {result.environment}
          </span>
        )}
        {Object.entries(result.providers ?? {}).map(([k, v]) => (
          <span className="meta-chip" key={k}>
            <strong>{k}</strong> {v}
          </span>
        ))}
      </div>

      <ResearchProcessPanel
        trace={result.trace ?? []}
        plannedStages={result.planned_stages ?? []}
        durationMs={durationMs}
        defaultOpen={defaultThinkingOpen}
        lang={lang}
      />

      {result.report && (
        <>
          <div className="section-label">{t('report')}</div>
          <Markdown>{result.report}</Markdown>
        </>
      )}

      {result.evidence?.length > 0 && (
        <>
          <div className="section-label">{t('evidence')}</div>
          {result.evidence.map((e, i) => (
            <div className="evidence-card" key={i}>
              <div className="evidence-source">
                {t('source')}: {e.source}
              </div>
              <div className="evidence-text">{e.summary}</div>
            </div>
          ))}
        </>
      )}
    </div>
  )
}
