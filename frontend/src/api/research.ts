import type { Lang, ResearchMode, ResearchRequest, RetrievalPlan, RunResult } from '../types'

export interface ResearchInput {
  question: string
  ticker: string | null
  lang: Lang
  selectedSkill: string | null
  mode: ResearchMode
}

/**
 * POST /v1/research/runs.
 *
 * IMPORTANT: this is a long blocking synchronous request — the backend runs the
 * entire research workflow before responding (can take tens of seconds). We do
 * NOT set an aggressive timeout and we do NOT poll; the caller drives an
 * optimistic "running" bubble client-side.
 */
export async function postResearchRun(input: ResearchInput): Promise<RunResult> {
  const body: ResearchRequest = {
    question: input.question,
    ticker: input.ticker,
    template: 'agent_analysis', // placeholder — backend ignores it
    lang: input.lang,
    selected_skill: input.selectedSkill,
    mode: input.mode,
  }
  const res = await fetch('/v1/research/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(text || `HTTP ${res.status} ${res.statusText}`)
  }
  return (await res.json()) as RunResult
}

/**
 * POST /v1/research/runs/{run_id}/approve.
 *
 * Resumes a run paused at `status: 'awaiting_approval'` (created via
 * `mode: 'plan'`), optionally substituting an edited `RetrievalPlan`, and
 * returns the final `RunResult`. Same long-blocking-request shape as
 * `postResearchRun` — no timeout/polling.
 */
export async function approveRun(runId: string, editedPlan?: RetrievalPlan | null): Promise<RunResult> {
  const res = await fetch(`/v1/research/runs/${encodeURIComponent(runId)}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ plan: editedPlan ?? null }),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(text || `HTTP ${res.status} ${res.statusText}`)
  }
  return (await res.json()) as RunResult
}
