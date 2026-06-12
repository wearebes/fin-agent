import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Check, Pencil, X } from 'lucide-react'
import { approveRun } from '../api/research'
import { translate } from '../i18n'
import type { Lang, RetrievalPlan, RunResult } from '../types'
import { useWorkspace } from '../store/workspace'

function summarizePlan(plan: RetrievalPlan, t: (k: string) => string): { label: string; items: string[] }[] {
  const groups: { label: string; items: string[] }[] = []
  if (plan.search_queries.length) {
    groups.push({ label: t('planSearches'), items: plan.search_queries.map((q) => `"${q.query}" (max ${q.max_results})`) })
  }
  if (plan.market_data.length) {
    groups.push({ label: t('planMarketData'), items: plan.market_data.map((m) => `${m.ticker} (${m.asset_type}, ${m.period})`) })
  }
  if (plan.financials.length) {
    groups.push({ label: t('planFinancials'), items: plan.financials.map((f) => `${f.ticker} ${f.statement_type}`) })
  }
  if (plan.fetch_company_info_tickers.length) groups.push({ label: t('planCompanyInfo'), items: plan.fetch_company_info_tickers })
  if (plan.fetch_analyst_data_tickers.length) groups.push({ label: t('planAnalystData'), items: plan.fetch_analyst_data_tickers })
  if (plan.fetch_crypto_tickers.length) groups.push({ label: t('planCryptoData'), items: plan.fetch_crypto_tickers })
  return groups
}

export default function PlanApprovalPanel({
  result,
  messageId,
  lang,
}: {
  result: RunResult
  messageId: string
  lang: Lang
}) {
  const t = (k: string) => translate(lang, k)
  const updateMessage = useWorkspace((s) => s.updateMessage)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [jsonError, setJsonError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: ({ runId, plan }: { runId: string; plan: RetrievalPlan | null }) => approveRun(runId, plan),
  })

  const plan = result.plan
  if (!plan) return null  // defensive — backend guarantees `plan` is populated whenever status === 'awaiting_approval'

  const groups = summarizePlan(plan, t)

  const startEditing = () => {
    setDraft(JSON.stringify(plan, null, 2))
    setJsonError(null)
    setEditing(true)
  }

  const submitApproval = (editedPlan: RetrievalPlan | null) => {
    mutation.mutate(
      { runId: result.run_id, plan: editedPlan },
      {
        onSuccess: (finalResult) => updateMessage(messageId, { result: finalResult }),
        onError: (error) =>
          updateMessage(messageId, {
            status: 'failed',
            error: error instanceof Error ? error.message : String(error),
          }),
      },
    )
  }

  const onApprove = () => submitApproval(null)

  const onApproveEdited = () => {
    let parsed: unknown
    try {
      parsed = JSON.parse(draft)
    } catch {
      setJsonError(t('planInvalidJson'))
      return
    }
    setJsonError(null)
    submitApproval(parsed as RetrievalPlan)
    setEditing(false)
  }

  const pending = mutation.isPending

  return (
    <div className="plan-panel">
      <div className="status-pill awaiting">
        <span className="status-dot" />
        {t('awaiting_approval')}
      </div>

      <div className="section-label">{t('planTitle')}</div>

      {!editing ? (
        <>
          {groups.length === 0 ? (
            <p className="plan-empty">{t('planEmpty')}</p>
          ) : (
            groups.map((g) => (
              <div className="plan-group" key={g.label}>
                <div className="plan-group-label">{g.label}</div>
                <ul className="plan-group-items">
                  {g.items.map((item, i) => <li key={i}>{item}</li>)}
                </ul>
              </div>
            ))
          )}
          <div className="plan-actions">
            <button className="ghost-btn" onClick={startEditing} disabled={pending}>
              <Pencil size={13} /> {t('planEdit')}
            </button>
            <button className="send-btn" onClick={onApprove} disabled={pending}>
              {pending ? <span className="spinner" /> : <Check size={15} />}
              {pending ? t('planSubmitting') : t('planApprove')}
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="plan-edit-hint">{t('planEditHint')}</p>
          <textarea
            className="plan-edit-textarea"
            value={draft}
            onChange={(e) => { setDraft(e.target.value); setJsonError(null) }}
            rows={14}
            spellCheck={false}
          />
          {jsonError && <p className="error-text">{jsonError}</p>}
          <div className="plan-actions">
            <button className="ghost-btn" onClick={() => setEditing(false)} disabled={pending}>
              <X size={13} /> {t('planCancel')}
            </button>
            <button className="send-btn" onClick={onApproveEdited} disabled={pending}>
              {pending ? <span className="spinner" /> : <Check size={15} />}
              {pending ? t('planSubmitting') : t('planApprove')}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
