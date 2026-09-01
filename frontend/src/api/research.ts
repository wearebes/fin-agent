import type {
  Lang, ResearchMode, ResearchProgress, ResearchRequest, ResearchTurn, RetrievalPlan, RunResult,
} from '../types'

export interface ResearchInput {
  question: string
  ticker: string | null
  lang: Lang
  selectedSkill: string | null
  mode: ResearchMode
  history?: ResearchTurn[]
}

async function checkResponse(response: Response): Promise<void> {
  if (response.ok) return
  const body = await response.json().catch(() => null)
  const detail = typeof body?.detail === 'string' ? body.detail : `HTTP ${response.status}`
  throw new Error(detail)
}

export async function postResearchRun(
  input: ResearchInput,
  onProgress?: (event: ResearchProgress) => void,
  personal?: { token: string; source?: 'personal' | 'codex' },
): Promise<RunResult> {
  const body: ResearchRequest = {
    question: input.question,
    ticker: input.ticker,
    template: 'agent_analysis',
    lang: input.lang,
    selected_skill: input.selectedSkill,
    mode: input.mode,
    history: input.history,
  }
  const options = {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(personal ? { Authorization: `Bearer ${personal.token}` } : {}) },
    body: JSON.stringify(body),
  }
  const endpoint = personal?.source === 'codex' ? '/v1/research/codex/stream'
    : personal ? '/v1/research/personal/stream' : '/v1/research/stream'
  const response = await fetch(endpoint, options)
  // Only an unsupported endpoint is safe to retry through the legacy API.
  if (response.status === 404 || response.status === 405) {
    if (personal) throw new Error('所选个人 API / Codex 入口不可用；不会改用其他模型或密钥。 / Selected model endpoint unavailable; no fallback.')
    if (input.history?.length) {
      throw new Error('请重启后端以启用连续追问。 / Restart the backend to enable conversation context.')
    }
    const legacy = await fetch('/v1/research/runs', options)
    await checkResponse(legacy)
    return legacy.json() as Promise<RunResult>
  }
  await checkResponse(response)
  if (!response.body || !response.headers.get('content-type')?.includes('text/event-stream')) {
    throw new Error('Invalid research stream / 研究进度响应格式错误')
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { value, done } = await reader.read()
      buffer = (buffer + decoder.decode(value, { stream: !done })).replace(/\r\n/g, '\n')
      let boundary: number
      while ((boundary = buffer.indexOf('\n\n')) !== -1) {
        const lines = buffer.slice(0, boundary).split('\n')
        buffer = buffer.slice(boundary + 2)
        const event = lines.find((line) => line.startsWith('event:'))?.slice(6).trim()
        const data = lines.filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trimStart()).join('\n')
        if (!data || !event) continue
        const payload = JSON.parse(data)
        if (event === 'progress') onProgress?.(payload as ResearchProgress)
        if (event === 'result') return payload as RunResult
        if (event === 'error') throw new Error(payload.message || 'Research failed')
      }
      if (done) break
    }
    throw new Error('连接中断，结果未确认，请勿立即重复提交。 / Stream interrupted; result unconfirmed.')
  } finally {
    await reader.cancel().catch(() => undefined)
    reader.releaseLock()
  }
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
