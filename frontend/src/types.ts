// Manual mirror of the backend pydantic models in
// src/fin_agent/domain/types.py. Keep field names/types in sync.

export type RunStatus = 'pending' | 'running' | 'completed' | 'failed'
export type Lang = 'zh' | 'en'

export interface ResearchRequest {
  question: string
  ticker: string | null
  // `template` is a placeholder: the backend currently IGNORES it (it always
  // runs `open_research`). We send `agent_analysis` for parity with the legacy
  // frontend; do not expect it to change backend behavior.
  template: string
  lang: Lang
}

export interface EvidenceItem {
  source: string
  summary: string
}

export interface TraceRecord {
  stage: string
  detail: string
}

export interface RunResult {
  run_id: string
  status: RunStatus
  environment: string
  request: ResearchRequest
  providers: Record<string, string>
  planned_stages: string[]
  report: string
  evidence: EvidenceItem[]
  trace: TraceRecord[]
}
