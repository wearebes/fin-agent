import { useMemo, useState, type CSSProperties, type FormEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  Activity,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  CircleX,
  CircleHelp,
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
  type CustomSignalKind,
  type ForensicsInput,
  type ForensicsReport,
  type StrategyKind,
} from '../api/forensics'
import { useWorkspace } from '../store/workspace'

const copy = {
  zh: {
    eyebrow: '策略评估',
    tabSetup: '策略配置', tabBacktest: '回测对比', tabForensics: '策略评估',
    backtestEmpty: '请先完成策略配置并运行回测。', forensicsEmpty: '请先运行回测，策略评估才有证据可检查。',
    configure: '策略配置',
    ticker: '标的代码', benchmark: '基准（可选）', period: '历史区间', cost: '单边交易成本',
    windows: '参数窗口', fast: '快速', slow: '慢速', run: '开始回测分析',
    running: '正在获取行情并审计…', presets: '策略模板', introTitle: '检查范围',
    evidenceNames: ['未来数据泄漏', '过拟合', '参数敏感性', '交易成本', '市场状态', 'Alpha 真实性'],
    reliability: '策略可信度', annualized: '年化收益', drawdown: '最大回撤', chartReturn: '收益率',
    sharpe: '夏普比率', alpha: '年化 Alpha', curve: '净值证据', strategy: '组合',
    base: '基准', checks: '策略检查', sensitivity: '参数敏感度', costs: '成本压力测试',
    regimes: '市场状态归因', aiNote: 'AI 分析摘要', ruleNote: '规则摘要',
    primary: '主要风险来源', repair: '最小修复建议', observations: '个交易日', trades: '次换仓',
    source: '历史收盘价', error: '分析未完成', retry: '检查代码或更换标的后重试。',
    customName: '规则名称', customSignal: '信号指标', entry: '入场阈值', exit: '离场阈值',
    customHint: {
      ma_cross: '阈值为快慢均线差（%）：高于入场值持有，低于离场值空仓。',
      rsi: '阈值为 RSI：低于入场值买入，高于离场值卖出。',
      momentum: '阈值为区间动量（%）：高于入场值持有，低于离场值空仓。',
      bollinger: '阈值为标准差倍数：跌破入场倍数买入，回到离场倍数卖出。',
    },
    tickerHelp: {
      trigger: '查看标的代码说明', close: '收起说明', title: '标的怎么填？',
      note: '可直接填常用简称，系统会自动转换为行情代码；不需要记忆 ^ 等特殊符号。',
      examples: [['比亚迪', '002594'], ['纳斯达克 100', 'NDX100'], ['纳指 100 ETF', 'QQQ'], ['苹果', 'AAPL']],
    },
    benchmarkHelp: {
      trigger: '查看基准说明', close: '收起说明', title: '基准怎么选？',
      note: '可留空：只评估策略自身表现。需要比较相对收益时，选择与标的市场相近的宽基。',
      examples: [['沪深 300', '000300'], ['标普 500', 'SPY'], ['纳斯达克 100', 'NDX100'], ['恒生指数', '^HSI']],
    },
  },
  en: {
    eyebrow: 'Strategy Evaluation',
    tabSetup: 'Strategy configuration', tabBacktest: 'Backtest comparison', tabForensics: 'Strategy evaluation',
    backtestEmpty: 'Configure a strategy and run a backtest first.', forensicsEmpty: 'Run a backtest first so the strategy evaluation has evidence.',
    configure: 'Strategy configuration',
    ticker: 'Ticker', benchmark: 'Benchmark (optional)', period: 'History', cost: 'One-way cost',
    windows: 'Parameter windows', fast: 'Fast', slow: 'Slow', run: 'Run backtest analysis',
    running: 'Fetching prices and auditing…', presets: 'Templates', introTitle: 'Audit coverage',
    evidenceNames: ['Leakage', 'Overfitting', 'Sensitivity', 'Costs', 'Regimes', 'Alpha'],
    reliability: 'Reliability', annualized: 'Annual return', drawdown: 'Max drawdown', chartReturn: 'Return',
    sharpe: 'Sharpe ratio', alpha: 'Annual alpha', curve: 'Equity evidence', strategy: 'Portfolio',
    base: 'Benchmark', checks: 'Strategy checks', sensitivity: 'Parameter sensitivity',
    costs: 'Cost stress', regimes: 'Regime attribution', aiNote: 'AI analysis brief',
    ruleNote: 'Rules summary', primary: 'Primary risk', repair: 'Minimum repair',
    observations: 'sessions', trades: 'trades', source: 'Historical closes',
    error: 'Analysis did not complete', retry: 'Check the symbol or try another instrument.',
    customName: 'Rule name', customSignal: 'Signal indicator', entry: 'Entry threshold', exit: 'Exit threshold',
    customHint: {
      ma_cross: 'Thresholds are MA spread (%): hold above entry and exit below the exit value.',
      rsi: 'Thresholds are RSI: enter below entry and exit above the exit value.',
      momentum: 'Thresholds are lookback momentum (%): hold above entry and exit below the exit value.',
      bollinger: 'Thresholds are standard deviations: enter below the lower band and exit at the exit band.',
    },
    tickerHelp: {
      trigger: 'Show ticker guidance', close: 'Hide guidance', title: 'How do I enter a ticker?',
      note: 'Common names are accepted and converted to market symbols automatically.',
      examples: [['BYD', '002594'], ['Nasdaq 100', 'NDX100'], ['Nasdaq 100 ETF', 'QQQ'], ['Apple', 'AAPL']],
    },
    benchmarkHelp: {
      trigger: 'Show benchmark guidance', close: 'Hide guidance', title: 'How do I choose a benchmark?',
      note: 'Leave blank for absolute performance; otherwise choose a broad index from the same market.',
      examples: [['CSI 300', '000300'], ['S&P 500', 'SPY'], ['Nasdaq 100', 'NDX100'], ['Hang Seng', '^HSI']],
    },
  },
}

type Labels = typeof copy.zh
type WorkbenchTab = 'setup' | 'backtest' | 'forensics'

const templates: Array<{ kind: StrategyKind; zh: string; en: string; fast: number; slow: number }> = [
  { kind: 'ma_cross', zh: '双均线趋势', en: 'Dual MA trend', fast: 20, slow: 60 },
  { kind: 'breakout', zh: '区间突破', en: 'Range breakout', fast: 10, slow: 55 },
  { kind: 'mean_reversion', zh: '均值回归', en: 'Mean reversion', fast: 10, slow: 40 },
  { kind: 'rsi_reversion', zh: 'RSI 反转', en: 'RSI reversal', fast: 14, slow: 60 },
  { kind: 'momentum_trend', zh: '动量趋势', en: 'Momentum trend', fast: 20, slow: 60 },
  { kind: 'bollinger_reversion', zh: '布林带反转', en: 'Bollinger reversion', fast: 20, slow: 60 },
  { kind: 'custom', zh: '自定义规则', en: 'Custom rule', fast: 20, slow: 60 },
]

const customSignals: Array<{ kind: CustomSignalKind; zh: string; en: string }> = [
  { kind: 'ma_cross', zh: '均线差', en: 'MA spread' },
  { kind: 'rsi', zh: 'RSI', en: 'RSI' },
  { kind: 'momentum', zh: '区间动量', en: 'Momentum' },
  { kind: 'bollinger', zh: '布林带', en: 'Bollinger bands' },
]

const customDefaults: Record<CustomSignalKind, { entry: number; exit: number }> = {
  ma_cross: { entry: 0.2, exit: 0 }, rsi: { entry: 30, exit: 55 },
  momentum: { entry: 2, exit: 0 }, bollinger: { entry: 2, exit: 0 },
}

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

function EquityChart({ report, labels }: { report: ForensicsReport; labels: Labels }) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)
  const points = useMemo(() => {
    const hasBenchmark = report.equity_curve.some((point) => point.benchmark !== null)
    const all = report.equity_curve.flatMap((point) =>
      point.benchmark === null ? [point.strategy] : [point.strategy, point.benchmark]
    )
    const low = Math.min(...all)
    const high = Math.max(...all)
    const span = Math.max(1, high - low)
    const toY = (value: number) => 225 - ((value - low) / span) * 190
    const map = (key: 'strategy' | 'benchmark') => report.equity_curve.map((point, index) => {
      const x = (index / Math.max(1, report.equity_curve.length - 1)) * 900
      const y = toY(point[key] ?? point.strategy)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    }).join(' ')
    return {
      strategy: map('strategy'), benchmark: hasBenchmark ? map('benchmark') : '',
      hasBenchmark, low, high, toY,
    }
  }, [report])

  const baseStrategy = report.equity_curve[0]?.strategy || 1
  const baseBenchmark = report.equity_curve[0]?.benchmark || 1
  const hovered = hoverIndex === null ? null : report.equity_curve[hoverIndex]
  const hoverX = hoverIndex === null ? 0 : (hoverIndex / Math.max(1, report.equity_curve.length - 1)) * 900
  const updateHover = (clientX: number, element: SVGSVGElement) => {
    const rect = element.getBoundingClientRect()
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
    setHoverIndex(Math.round(ratio * Math.max(0, report.equity_curve.length - 1)))
  }

  return (
    <div className="qf-chart-wrap" onPointerLeave={() => setHoverIndex(null)}>
      <svg className="qf-chart" viewBox="0 0 900 250" role="img" aria-label="Strategy and benchmark equity curve" onPointerMove={(event) => updateHover(event.clientX, event.currentTarget)}>
        {[35, 82.5, 130, 177.5, 225].map((y) => <line key={y} x1="0" x2="900" y1={y} y2={y} className="qf-gridline" />)}
        {points.hasBenchmark && <polyline points={points.benchmark} className="qf-line qf-line-base" />}
        <polyline points={points.strategy} className="qf-line qf-line-strategy" />
        {hovered && <g className="qf-chart-crosshair" aria-hidden="true">
          <line x1={hoverX} x2={hoverX} y1="20" y2="230" />
          <line x1="0" x2="900" y1={points.toY(hovered.strategy)} y2={points.toY(hovered.strategy)} />
          <circle cx={hoverX} cy={points.toY(hovered.strategy)} r="4" className="strategy" />
          {points.hasBenchmark && hovered.benchmark !== null && <circle cx={hoverX} cy={points.toY(hovered.benchmark)} r="4" className="benchmark" />}
        </g>}
        <rect className="qf-chart-hitbox" x="0" y="0" width="900" height="250" />
      </svg>
      <div className="qf-chart-axis"><span>{formatPct(((points.low / baseStrategy) - 1) * 100)}</span><span>{formatPct(((points.high / baseStrategy) - 1) * 100)}</span></div>
      <span className="qf-chart-axis-title">{labels.chartReturn}</span>
      {hovered && <div className="qf-chart-tooltip" style={{ left: `${Math.min(88, Math.max(12, (hoverX / 900) * 100))}%` }}>
        <strong>{hovered.date}</strong>
        <div><span><i className="strategy" />{labels.strategy}</span><b>{formatPct(((hovered.strategy / baseStrategy) - 1) * 100)}</b></div>
        {points.hasBenchmark && hovered.benchmark !== null && <div><span><i />{labels.base}</span><b>{formatPct(((hovered.benchmark / baseBenchmark) - 1) * 100)}</b></div>}
      </div>}
    </div>
  )
}

export default function QuantWorkbench() {
  const lang = useWorkspace((state) => state.lang)
  const labels = copy[lang]
  const [activeTab, setActiveTab] = useState<WorkbenchTab>('setup')
  const [help, setHelp] = useState<'ticker' | 'benchmark' | null>(null)
  const [form, setForm] = useState<ForensicsInput>({
    ticker: 'SPY', benchmark: '', period: '5y', strategy: 'ma_cross',
    fast_window: 20, slow_window: 60, custom_signal: 'ma_cross', entry_threshold: 0.2,
    exit_threshold: 0, strategy_name: '', transaction_cost_bps: 8, lang,
  })
  const mutation = useMutation({
    mutationFn: runForensics,
    onSuccess: () => setActiveTab('backtest'),
  })
  const update = <K extends keyof ForensicsInput>(key: K, value: ForensicsInput[K]) => {
    setForm((current) => ({ ...current, [key]: value }))
  }
  const toggleHelp = (target: 'ticker' | 'benchmark') => {
    setHelp((current) => current === target ? null : target)
  }
  const selectTemplate = (kind: StrategyKind) => {
    const template = templates.find((item) => item.kind === kind)!
    setForm((current) => ({
      ...current, strategy: kind, fast_window: template.fast, slow_window: template.slow,
    }))
  }
  const selectCustomSignal = (kind: CustomSignalKind) => {
    const defaults = customDefaults[kind]
    setForm((current) => ({
      ...current, custom_signal: kind, entry_threshold: defaults.entry, exit_threshold: defaults.exit,
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
          <div className="qf-panel-heading"><h2>{labels.configure}</h2><FlaskConical size={24} /></div>
          <label className="qf-label">{labels.presets}</label>
          <div className="qf-template-grid">
            {templates.map((template) => <button type="button" key={template.kind} onClick={() => selectTemplate(template.kind)} className={form.strategy === template.kind ? 'active' : ''}><Activity size={16} /><span>{template[lang]}</span></button>)}
          </div>
          {form.strategy === 'custom' && <>
            <div className="qf-fields qf-fields-2">
              <label><span>{labels.customName}</span><input value={form.strategy_name} maxLength={40} onChange={(event) => update('strategy_name', event.target.value)} placeholder={lang === 'zh' ? '例如：低波动均线规则' : 'e.g. Low-volatility MA rule'} /></label>
              <label><span>{labels.customSignal}</span><select value={form.custom_signal} onChange={(event) => selectCustomSignal(event.target.value as CustomSignalKind)}>{customSignals.map((signal) => <option key={signal.kind} value={signal.kind}>{signal[lang]}</option>)}</select></label>
            </div>
            <div className="qf-fields qf-fields-2">
              <label><span>{labels.entry}</span><input type="number" step="0.1" value={form.entry_threshold} onChange={(event) => update('entry_threshold', Number(event.target.value))} /></label>
              <label><span>{labels.exit}</span><input type="number" step="0.1" value={form.exit_threshold} onChange={(event) => update('exit_threshold', Number(event.target.value))} /></label>
            </div>
            <p className="qf-custom-hint">{labels.customHint[form.custom_signal]}</p>
          </>}
          <div className="qf-fields qf-fields-2">
            <label><span>{labels.ticker}<button className="qf-help-trigger" type="button" aria-label={labels.tickerHelp.trigger} aria-expanded={help === 'ticker'} onClick={() => toggleHelp('ticker')}><CircleHelp size={14} /></button></span><input value={form.ticker} onChange={(event) => update('ticker', event.target.value)} placeholder="002594 / NDX100 / AAPL" required /></label>
            <label><span>{labels.benchmark}<button className="qf-help-trigger" type="button" aria-label={labels.benchmarkHelp.trigger} aria-expanded={help === 'benchmark'} onClick={() => toggleHelp('benchmark')}><CircleHelp size={14} /></button></span><input value={form.benchmark} onChange={(event) => update('benchmark', event.target.value)} placeholder={lang === 'zh' ? '可留空；需要比较时再填写' : 'Optional; add only for comparison'} /></label>
          </div>
          {help && <aside className="qf-code-help" role="note"><header><strong>{labels[`${help}Help`].title}</strong><button type="button" onClick={() => setHelp(null)}>{labels[`${help}Help`].close}</button></header><p>{labels[`${help}Help`].note}</p><div className="qf-symbol-examples">{labels[`${help}Help`].examples.map(([name, symbol]) => <button type="button" key={symbol} onClick={() => { update(help, symbol); setHelp(null) }}><span>{name}</span><b>{symbol}</b></button>)}</div></aside>}
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
      <div className="qf-intro-list">
        {labels.evidenceNames.map((item) => <div key={item}><CheckCircle2 size={14} />{item}</div>)}
      </div>
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
    ...(report.metrics.alpha_pct === null ? [] : [[labels.alpha, formatPct(report.metrics.alpha_pct)] as const]),
  ]
  const weakest = [...report.checks].sort((a, b) => a.score - b.score)[0]
  return <section className="qf-report">
    {view === 'backtest' && <>
      <div className="qf-report-head"><div><span>BACKTEST / {report.run_id}</span><h2>{report.ticker} · {report.strategy_label}</h2></div><div>{report.data_start} → {report.data_end}<br />{labels.source}</div></div>
      <div className="qf-metrics">{metrics.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
      <article className="qf-card qf-equity"><div className="qf-card-title"><div><span>HISTORICAL COMPARISON</span><h3>{labels.curve}</h3></div><div className="qf-legend"><span><i className="strategy" />{labels.strategy}</span>{report.benchmark && <span><i />{labels.base}</span>}</div></div><EquityChart report={report} labels={labels} /></article>
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
