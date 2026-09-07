import { useMemo, useState, type CSSProperties, type FormEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  Activity,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  CircleX,
  FlaskConical,
  Gauge,
  Play,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from 'lucide-react'
import {
  runForensics,
  type AuditCheck,
  type ForensicsInput,
  type ForensicsReport,
  type StrategyKind,
} from '../api/forensics'
import { useWorkspace } from '../store/workspace'

const copy = {
  zh: {
    eyebrow: '策略法医',
    tabSetup: '策略设置', tabBacktest: '回测对比', tabForensics: '策略法医',
    backtestEmpty: '先完成策略设置并运行回测。', forensicsEmpty: '先运行回测，策略法医才有证据可检查。',
    desc: '用真实历史行情检查未来数据泄漏、过拟合、参数脆弱性、交易成本、市场状态依赖与伪 Alpha。',
    guardrail: 'AI 只解释证据，不改写回测数字', configure: '送检策略',
    configureDesc: '选择一个可复现策略模板，设定参数后启动完整审计。',
    ticker: '标的代码', benchmark: '基准', period: '历史区间', cost: '单边交易成本',
    windows: '参数窗口', fast: '快速', slow: '慢速', run: '开始策略尸检',
    running: '正在获取行情并审计…', presets: '策略模板', introTitle: '检查范围',
    evidenceNames: ['未来数据泄漏', '过拟合', '参数敏感性', '交易成本', '市场状态', 'Alpha 真实性'],
    introDesc: '系统使用滞后一日的信号执行回测，并用锁定规则完成诊断。最终输出不是买卖建议，而是一份可复核的策略可靠性报告。',
    reliability: '策略可信度', annualized: '年化收益', drawdown: '最大回撤',
    sharpe: '夏普比率', alpha: '年化 Alpha', curve: '净值证据', strategy: '策略',
    base: '基准', checks: '法医检查', sensitivity: '参数敏感度', costs: '成本压力测试',
    regimes: '市场状态归因', aiNote: 'AI 法医摘要', ruleNote: '规则引擎摘要',
    primary: '主要死因', repair: '最小修复建议', observations: '个交易日', trades: '次换仓',
    source: '历史收盘价', error: '审计未完成', retry: '检查代码或更换标的后重试。',
  },
  en: {
    eyebrow: 'Quant Forensics',
    tabSetup: 'Strategy setup', tabBacktest: 'Backtest comparison', tabForensics: 'Strategy forensics',
    backtestEmpty: 'Set up a strategy and run a backtest first.', forensicsEmpty: 'Run a backtest first so the forensic checks have evidence.',
    desc: 'Audit look-ahead leakage, overfitting, parameter fragility, costs, regime dependence, and false alpha on real historical prices.',
    guardrail: 'AI explains evidence; it cannot rewrite backtest numbers', configure: 'Submit a strategy',
    configureDesc: 'Pick a reproducible template, set its parameters, and run the locked audit.',
    ticker: 'Ticker', benchmark: 'Benchmark', period: 'History', cost: 'One-way cost',
    windows: 'Parameter windows', fast: 'Fast', slow: 'Slow', run: 'Start autopsy',
    running: 'Fetching prices and auditing…', presets: 'Templates', introTitle: 'Audit coverage',
    evidenceNames: ['Leakage', 'Overfitting', 'Sensitivity', 'Costs', 'Regimes', 'Alpha'],
    introDesc: 'Signals are lagged by one session and every diagnosis follows locked rules. The output is an inspectable reliability report, not trading advice.',
    reliability: 'Reliability', annualized: 'Annual return', drawdown: 'Max drawdown',
    sharpe: 'Sharpe ratio', alpha: 'Annual alpha', curve: 'Equity evidence', strategy: 'Strategy',
    base: 'Benchmark', checks: 'Forensic checks', sensitivity: 'Parameter sensitivity',
    costs: 'Cost stress', regimes: 'Regime attribution', aiNote: 'AI forensic brief',
    ruleNote: 'Rules-engine brief', primary: 'Primary failure', repair: 'Minimum repair',
    observations: 'sessions', trades: 'trades', source: 'Historical closes',
    error: 'Audit did not complete', retry: 'Check the symbol or try another instrument.',
  },
}

type Labels = typeof copy.zh
type WorkbenchTab = 'setup' | 'backtest' | 'forensics'

const templates: Array<{ kind: StrategyKind; zh: string; en: string; fast: number; slow: number }> = [
  { kind: 'ma_cross', zh: '双均线趋势', en: 'Dual MA trend', fast: 20, slow: 60 },
  { kind: 'breakout', zh: '区间突破', en: 'Range breakout', fast: 10, slow: 55 },
  { kind: 'mean_reversion', zh: '均值回归', en: 'Mean reversion', fast: 10, slow: 40 },
]

const regimeLabels: Record<string, { zh: string; en: string }> = {
  bull: { zh: '上涨环境', en: 'Bull' },
  bear: { zh: '下跌环境', en: 'Bear' },
  high_vol: { zh: '高波动', en: 'High vol' },
}

function formatPct(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

function StatusIcon({ check }: { check: AuditCheck }) {
  if (check.status === 'pass') return <CheckCircle2 size={18} />
  if (check.status === 'warning') return <TriangleAlert size={18} />
  return <CircleX size={18} />
}

function EquityChart({ report }: { report: ForensicsReport }) {
  const points = useMemo(() => {
    const all = report.equity_curve.flatMap((point) => [point.strategy, point.benchmark])
    const low = Math.min(...all)
    const high = Math.max(...all)
    const span = Math.max(1, high - low)
    const map = (key: 'strategy' | 'benchmark') => report.equity_curve.map((point, index) => {
      const x = (index / Math.max(1, report.equity_curve.length - 1)) * 900
      const y = 225 - ((point[key] - low) / span) * 190
      return `${x.toFixed(1)},${y.toFixed(1)}`
    }).join(' ')
    return { strategy: map('strategy'), benchmark: map('benchmark'), min: low, max: high }
  }, [report])

  return (
    <div className="qf-chart-wrap">
      <svg className="qf-chart" viewBox="0 0 900 250" role="img" aria-label="Strategy and benchmark equity curve">
        {[35, 82.5, 130, 177.5, 225].map((y) => <line key={y} x1="0" x2="900" y1={y} y2={y} className="qf-gridline" />)}
        <polyline points={points.benchmark} className="qf-line qf-line-base" />
        <polyline points={points.strategy} className="qf-line qf-line-strategy" />
      </svg>
      <div className="qf-chart-axis"><span>{points.min.toFixed(0)}</span><span>{points.max.toFixed(0)}</span></div>
    </div>
  )
}

export default function QuantWorkbench() {
  const lang = useWorkspace((state) => state.lang)
  const labels = copy[lang]
  const [activeTab, setActiveTab] = useState<WorkbenchTab>('setup')
  const [form, setForm] = useState<ForensicsInput>({
    ticker: 'SPY', benchmark: 'SPY', period: '5y', strategy: 'ma_cross',
    fast_window: 20, slow_window: 60, transaction_cost_bps: 8, lang,
  })
  const mutation = useMutation({
    mutationFn: runForensics,
    onSuccess: () => setActiveTab('backtest'),
  })
  const update = <K extends keyof ForensicsInput>(key: K, value: ForensicsInput[K]) => {
    setForm((current) => ({ ...current, [key]: value }))
  }
  const selectTemplate = (kind: StrategyKind) => {
    const template = templates.find((item) => item.kind === kind)!
    setForm((current) => ({
      ...current, strategy: kind, fast_window: template.fast, slow_window: template.slow,
    }))
  }
  const submit = (event: FormEvent) => {
    event.preventDefault()
    mutation.mutate({
      ...form, ticker: form.ticker.trim().toUpperCase(),
      benchmark: form.benchmark.trim().toUpperCase(), lang,
    })
  }

  return (
    <section className="qf-page" aria-label={labels.eyebrow}>
      <nav className="qf-tabs" aria-label={labels.eyebrow} role="tablist">
        {([
          ['setup', labels.tabSetup],
          ['backtest', labels.tabBacktest],
          ['forensics', labels.tabForensics],
        ] as const).map(([tab, label]) => (
          <button key={tab} type="button" role="tab" aria-selected={activeTab === tab} onClick={() => setActiveTab(tab)}>
            {label}
          </button>
        ))}
      </nav>

      {activeTab === 'setup' && <section className="qf-shell" role="tabpanel">
        <form className="qf-panel qf-form" onSubmit={submit}>
          <div className="qf-panel-heading"><div><span>01 / INTAKE</span><h2>{labels.configure}</h2><p>{labels.configureDesc}</p></div><FlaskConical size={24} /></div>
          <label className="qf-label">{labels.presets}</label>
          <div className="qf-template-grid">
            {templates.map((template) => <button type="button" key={template.kind} onClick={() => selectTemplate(template.kind)} className={form.strategy === template.kind ? 'active' : ''}><Activity size={16} /><span>{template[lang]}</span></button>)}
          </div>
          <div className="qf-fields qf-fields-2">
            <label><span>{labels.ticker}</span><input value={form.ticker} onChange={(event) => update('ticker', event.target.value)} placeholder="SPY / AAPL / 510300" required /></label>
            <label><span>{labels.benchmark}</span><input value={form.benchmark} onChange={(event) => update('benchmark', event.target.value)} placeholder="SPY" required /></label>
          </div>
          <div className="qf-fields qf-fields-2">
            <label><span>{labels.period}</span><select value={form.period} onChange={(event) => update('period', event.target.value as ForensicsInput['period'])}><option value="1y">1 year</option><option value="2y">2 years</option><option value="5y">5 years</option><option value="10y">10 years</option></select></label>
            <label><span>{labels.cost}</span><div className="qf-unit-input"><input type="number" min="0" max="100" value={form.transaction_cost_bps} onChange={(event) => update('transaction_cost_bps', Number(event.target.value))} /><em>bps</em></div></label>
          </div>
          <label className="qf-label">{labels.windows}</label>
          <div className="qf-window-grid">
            <label><span>{labels.fast}</span><input type="number" min="3" max="120" value={form.fast_window} onChange={(event) => update('fast_window', Number(event.target.value))} /></label>
            <ArrowRight size={16} />
            <label><span>{labels.slow}</span><input type="number" min="10" max="260" value={form.slow_window} onChange={(event) => update('slow_window', Number(event.target.value))} /></label>
          </div>
          <button className="qf-run" type="submit" disabled={mutation.isPending || form.fast_window >= form.slow_window}>{mutation.isPending ? <><span className="qf-spinner" />{labels.running}</> : <><Play size={17} fill="currentColor" />{labels.run}</>}</button>
        </form>

        {!mutation.error && !mutation.isPending && <Intro labels={labels} />}
        {mutation.error && <div className="qf-panel qf-error"><CircleX size={36} /><h2>{labels.error}</h2><p>{mutation.error.message}</p><span>{labels.retry}</span></div>}
        {mutation.isPending && <div className="qf-panel qf-loading"><div className="qf-radar"><ScanSearch size={34} /></div><h2>{labels.running}</h2><p>Point-in-time signals · Locked costs · Chronological folds</p></div>}
      </section>}

      {activeTab !== 'setup' && (mutation.data ? (
        <section className="qf-results" role="tabpanel">
          <ScoreCard report={mutation.data} labels={labels} />
          <Report report={mutation.data} lang={lang} labels={labels} view={activeTab} />
        </section>
      ) : <EmptyResult labels={labels} tab={activeTab} />)}
    </section>
  )
}

function EmptyResult({ labels, tab }: { labels: Labels; tab: Exclude<WorkbenchTab, 'setup'> }) {
  return <div className="qf-panel qf-empty" role="tabpanel"><ScanSearch size={27} /><p>{tab === 'backtest' ? labels.backtestEmpty : labels.forensicsEmpty}</p></div>
}

function Intro({ labels }: { labels: Labels }) {
  return (
    <div className="qf-panel qf-intro">
      <h2>{labels.introTitle}</h2>
      <p>{labels.desc}</p>
      <div className="qf-intro-list">
        {labels.evidenceNames.map((item) => <div key={item}><CheckCircle2 size={14} />{item}</div>)}
      </div>
      <p>{labels.introDesc}</p>
      <p className="qf-note"><ShieldCheck size={16} />{labels.guardrail}</p>
    </div>
  )
}

function ScoreCard({ report, labels }: { report: ForensicsReport; labels: Labels }) {
  const scoreStyle = { '--qf-score': `${report.reliability_score * 3.6}deg` } as CSSProperties
  return <div className="qf-panel qf-score-card"><div className="qf-score-ring" style={scoreStyle}><div><strong>{report.reliability_score}</strong><span>/100</span></div></div><div className="qf-score-copy"><span>{labels.reliability}</span><h2>{report.verdict}</h2><p>{report.narrative.summary}</p><div className="qf-score-meta"><span><BarChart3 size={14} />{report.observation_count} {labels.observations}</span><span><Activity size={14} />{report.metrics.trade_count} {labels.trades}</span></div></div></div>
}

function Report({ report, lang, labels, view }: { report: ForensicsReport; lang: 'zh' | 'en'; labels: Labels; view: Exclude<WorkbenchTab, 'setup'> }) {
  const metrics = [
    [labels.annualized, formatPct(report.metrics.annualized_return_pct)],
    [labels.drawdown, formatPct(report.metrics.max_drawdown_pct)],
    [labels.sharpe, report.metrics.sharpe_ratio.toFixed(2)],
    [labels.alpha, formatPct(report.metrics.alpha_pct)],
  ]
  const weakest = [...report.checks].sort((a, b) => a.score - b.score)[0]
  return <section className="qf-report">
    {view === 'backtest' && <>
      <div className="qf-report-head"><div><span>BACKTEST / {report.run_id}</span><h2>{report.ticker} · {report.strategy_label}</h2></div><div>{report.data_start} → {report.data_end}<br />{labels.source}</div></div>
      <div className="qf-metrics">{metrics.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
      <article className="qf-card qf-equity"><div className="qf-card-title"><div><span>HISTORICAL COMPARISON</span><h3>{labels.curve}</h3></div><div className="qf-legend"><span><i className="strategy" />{labels.strategy}</span><span><i />{labels.base}</span></div></div><EquityChart report={report} /></article>
    </>}
    {view === 'forensics' && <>
      <article className="qf-card qf-narrative"><div className="qf-ai-tag"><Sparkles size={14} />{report.narrative.generated_by_ai ? labels.aiNote : labels.ruleNote}</div><blockquote>{report.narrative.summary}</blockquote><div><span>{labels.primary}</span><p>{report.narrative.primary_cause}</p></div><div><span>{labels.repair}</span><p>{report.narrative.repair_action}</p></div></article>
      <div className="qf-section-title"><div><span>DIAGNOSIS</span><h2>{labels.checks}</h2></div><Gauge size={24} /></div>
      <div className="qf-check-grid">{report.checks.map((check) => <article key={check.key} className={`qf-check ${check.status} ${check.key === weakest.key ? 'weakest' : ''}`}><header><div className="qf-check-icon"><StatusIcon check={check} /></div><div><h3>{check.title}</h3><span>{check.status.toUpperCase()}</span></div><strong>{check.score}</strong></header><p>{check.finding}</p><footer>{check.evidence}</footer></article>)}</div>
      <div className="qf-analysis-grid">
        <article className="qf-card"><div className="qf-card-title"><div><span>ROBUSTNESS</span><h3>{labels.sensitivity}</h3></div></div><div className="qf-bar-list">{report.sensitivity.map((point) => { const width = Math.min(100, Math.max(4, 50 + point.total_return_pct)); return <div key={point.label}><span>{point.label}<small>{point.fast_window}/{point.slow_window}</small></span><div><i style={{ width: `${width}%` }} /></div><strong>{formatPct(point.total_return_pct)}</strong></div>})}</div></article>
        <article className="qf-card"><div className="qf-card-title"><div><span>EXECUTION</span><h3>{labels.costs}</h3></div></div><div className="qf-cost-list">{report.cost_scenarios.map((item) => <div key={item.cost_bps}><span>{item.cost_bps} bps</span><i /><strong>{formatPct(item.total_return_pct)}</strong></div>)}</div></article>
        <article className="qf-card"><div className="qf-card-title"><div><span>REGIMES</span><h3>{labels.regimes}</h3></div></div><div className="qf-regimes">{report.regimes.map((item) => <div key={item.regime}><span>{regimeLabels[item.regime]?.[lang] || item.regime}</span><strong>{formatPct(item.annualized_return_pct)}</strong><small>{item.trading_days} {labels.observations}</small></div>)}</div></article>
      </div>
    </>}
    <div className="qf-disclaimer"><ShieldCheck size={16} />{report.disclaimer}</div>
  </section>
}
