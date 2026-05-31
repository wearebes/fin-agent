import type { Lang, ResearchRequest, RunResult } from '../types'

export interface ResearchInput {
  question: string
  ticker: string | null
  lang: Lang
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
