// Manual mirror of the backend pydantic models in
// src/fin_agent/domain/types.py. Keep field names/types in sync.

export type RunStatus = 'pending' | 'running' | 'completed' | 'awaiting_approval' | 'failed'
export type Lang = 'zh' | 'en'

// `mode: 'plan'` makes the backend run only `intake`+`plan`, return a
// `RunResult` with `status: 'awaiting_approval'` and a populated `plan`, and
// pause for review. `'auto'` (the default) preserves today's single-shot
// behavior end to end.
export type ResearchMode = 'auto' | 'plan'

export interface ResearchTurn {
  question: string
  answer: string
  ticker: string | null
}

export interface ResearchProgress {
  stage: string
  status: 'running' | 'completed' | 'failed' | 'skipped'
}

export interface ResearchRequest {
  question: string
  ticker: string | null
  // `template` is a placeholder: the backend currently IGNORES it (it always
  // runs `open_research`). We send `agent_analysis` for parity with the legacy
  // frontend; do not expect it to change backend behavior.
  template: string
  lang: Lang
  // Name of a skill explicitly picked via the composer's '/' dropdown — an
  // opaque catalog key matching `Skill.name` from `GET /v1/skills`. Never
  // parsed from `question` server-side; `null` means "no skill selected".
  selected_skill: string | null
  mode: ResearchMode
  history?: ResearchTurn[]
}

export interface EvidenceItem {
  source: string
  summary: string
}

export interface TraceRecord {
  stage: string
  detail: string
}

export interface SearchPlanItem {
  query: string
  max_results: number
}

export interface MarketDataPlanItem {
  ticker: string
  asset_type: string
  frequency: string
  period: string
}

export interface FinancialsPlanItem {
  ticker: string
  statement_type: string
  frequency: string
}

export interface RetrievalPlan {
  search_queries: SearchPlanItem[]
  market_data: MarketDataPlanItem[]
  financials: FinancialsPlanItem[]
  fetch_company_info_tickers: string[]
  fetch_analyst_data_tickers: string[]
  fetch_crypto_tickers: string[]
}

export interface RunResult {
  run_id: string
  status: RunStatus
  environment: string
  request: ResearchRequest
  providers: Record<string, string>
  planned_stages: string[]
  plan: RetrievalPlan | null
  report: string
  evidence: EvidenceItem[]
  trace: TraceRecord[]
  report_data?: ReportData | null
}

export interface ReportChart {
  title: string
  kind: 'line' | 'bar'
  unit: string
  labels: string[]
  series: { name: string; values: (number | null)[] }[]
  source: string
  note: string
}

export interface ReportData {
  captured_at: string
  narrative: 'ai' | 'data_only'
  metrics: { label: string; value: number; unit: string; context: string }[]
  charts: ReportChart[]
  gaps: string[]
  summary: string[]
}

export interface ResearchJob {
  id: string
  client_id: string
  request: ResearchRequest
  source: 'default' | 'personal' | 'codex'
  status: 'queued' | 'running' | 'completed' | 'failed' | 'interrupted'
  stage: string
  created_at: string
  updated_at: string
  error: string | null
  result?: RunResult | null
}
