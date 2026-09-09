import { useRef, useState } from 'react'
import { Copy, Download, Printer } from 'lucide-react'
import { translate } from '../i18n'
import { reportMarkdown } from '../lib/research'
import type { Lang, RunResult, RunStatus } from '../types'
import Markdown from './Markdown'
import ResearchProcessPanel from './ResearchProcessPanel'
import EvidencePanel from './EvidencePanel'

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
  const [section, setSection] = useState(defaultThinkingOpen ? 'execution' : 'report')
  const [notice, setNotice] = useState('')
  const root = useRef<HTMLDivElement>(null)
  const exportText = () => reportMarkdown(result, lang)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(exportText())
      setNotice(t('copied'))
    } catch {
      setNotice(t('copyFailed'))
    }
  }
  const download = () => {
    const url = URL.createObjectURL(new Blob([exportText()], { type: 'text/markdown;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `fin-agent-${result.run_id.replace(/[^a-zA-Z0-9_-]/g, '')}.md`
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    setNotice(t('downloaded'))
  }
  const print = () => {
    root.current?.classList.add('print-target')
    try { window.print() } finally { root.current?.classList.remove('print-target') }
  }

  return (
    <div className="result" ref={root}>
      <div className="result-toolbar">
        <div className={`status-pill ${pillClass(result.status)}`}>
          <span className="status-dot" />
          {t(result.status)}
        </div>
        <div className="report-actions">
          <button type="button" onClick={copy}><Copy size={14} />{t('copyReport')}</button>
          <button type="button" onClick={download}><Download size={14} />{t('downloadReport')}</button>
          <button type="button" onClick={print}><Printer size={14} />{t('printReport')}</button>
        </div>
      </div>
      <p className="action-notice" role="status">{notice}</p>

      {result.status === 'failed' && (
        <p role="alert">
          {lang === 'zh'
            ? '本次研究未成功完成或未通过审查。下方内容仅供排查，请核对证据与执行记录。'
            : 'Research did not complete successfully or pass review. Verify the evidence and execution trace before using this report.'}
        </p>
      )}

      <nav className="result-tabs" aria-label={t('report')}>
        {['report', 'dataSources', 'execution'].map((key) => (
          <button type="button" key={key} aria-pressed={section === key}
            onClick={() => setSection(key)}>{t(key)}
            {key === 'dataSources' && <span>{result.evidence?.length ?? 0}</span>}
          </button>
        ))}
      </nav>
      <section className="result-panel" hidden={section !== 'report'} aria-label={t('report')}>
        {result.report ? <Markdown>{result.report}</Markdown> : <p>{t('noReport')}</p>}
      </section>
      <section className="result-panel" hidden={section !== 'dataSources'} aria-label={t('dataSources')}>
        <h3 className="print-only">{t('dataSources')}</h3>
        <EvidencePanel evidence={result.evidence ?? []} lang={lang} />
      </section>
      <section className="result-panel execution-panel" hidden={section !== 'execution'} aria-label={t('execution')}>
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
          defaultOpen={true}
          lang={lang}
        />
      </section>
    </div>
  )
}
