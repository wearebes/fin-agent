export type StrategyKind =
  | 'ma_cross'
  | 'breakout'
  | 'mean_reversion'
  | 'rsi_reversion'
  | 'momentum_trend'
  | 'bollinger_reversion'
  | 'custom'
export type CustomSignalKind = 'ma_cross' | 'rsi' | 'momentum' | 'bollinger'
export type AuditStatus = 'pass' | 'warning' | 'fail'

export interface ForensicsInput {
  ticker: string
  benchmark: string
  period: '1y' | '2y' | '5y' | '10y'
  strategy: StrategyKind
  fast_window: number
  slow_window: number
  custom_signal: CustomSignalKind
  entry_threshold: number
  exit_threshold: number
  strategy_name: string
  transaction_cost_bps: number
  lang: 'zh' | 'en'
}

export interface PerformanceMetrics {
  total_return_pct: number
  annualized_return_pct: number
  annualized_volatility_pct: number
  sharpe_ratio: number
  max_drawdown_pct: number
  win_rate_pct: number
  trade_count: number
  beta: number | null
  alpha_pct: number | null
}

export interface AuditCheck {
  key: string
  title: string
  status: AuditStatus
  score: number
  finding: string
  evidence: string
}

export interface ForensicsReport {
  run_id: string
  created_at: string
  ticker: string
  benchmark: string | null
  period: string
  strategy: StrategyKind
  strategy_label: string
  data_start: string
  data_end: string
  observation_count: number
  reliability_score: number
  verdict: string
  metrics: PerformanceMetrics
  benchmark_return_pct: number | null
  checks: AuditCheck[]
  sensitivity: Array<{ label: string; fast_window: number; slow_window: number; total_return_pct: number }>
  cost_scenarios: Array<{ cost_bps: number; total_return_pct: number }>
  regimes: Array<{ regime: string; trading_days: number; annualized_return_pct: number }>
  equity_curve: Array<{ date: string; strategy: number; benchmark: number | null }>
  narrative: { summary: string; primary_cause: string; repair_action: string; generated_by_ai: boolean }
  disclaimer: string
}

export async function runForensics(input: ForensicsInput): Promise<ForensicsReport> {
  const response = await fetch('/v1/quant/forensics/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail || `HTTP ${response.status} ${response.statusText}`)
  }
  return (await response.json()) as ForensicsReport
}
