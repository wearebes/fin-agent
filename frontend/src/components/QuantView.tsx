import { useRef, useState } from 'react'
import { Download, FlaskConical, Play, Upload } from 'lucide-react'
import { backtest, DEFAULT_PARAMS, equityCsv, parsePriceCsv, samplePriceCsv, tradesCsv } from '../lib/backtest'
import type { AverageKind, BacktestParams, MarketScenario } from '../lib/backtest'
import { useWorkspace } from '../store/workspace'
import EquityChart from './EquityChart'
import QuantComparison from './QuantComparison'
import type { QuantRun } from './QuantComparison'
import Starfield from './Starfield'

const SAMPLE = samplePriceCsv()

function downloadCsv(text: string, filename: string) {
  const url = URL.createObjectURL(new Blob(['\uFEFF', text], { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export default function QuantView() {
  const lang = useWorkspace((s) => s.lang)
  const zh = lang === 'zh'
  const text = (cn: string, en: string) => zh ? cn : en
  const [csv, setCsv] = useState(SAMPLE)
  const [params, setParams] = useState({ ...DEFAULT_PARAMS })
  const [source, setSource] = useState('sample:cycle')
  const [scenario, setScenario] = useState<MarketScenario>('cycle')
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState('')
  const [run, setRun] = useState<QuantRun>(() => ({ result: backtest(parsePriceCsv(SAMPLE), DEFAULT_PARAMS), source: 'sample:cycle', data: SAMPLE }))
  const [reference, setReference] = useState<QuantRun | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const result = run.result
  const percent = (value: number) => `${(value * 100).toFixed(2)}%`
  const number = (value: number) => value.toLocaleString(zh ? 'zh-CN' : 'en-US', { maximumFractionDigits: 2 })
  const scenarioNames: Record<MarketScenario, string> = {
    cycle: text('区间震荡', 'Range-bound'), trend: text('趋势上涨', 'Uptrend'), drawdown: text('急跌与修复', 'Drawdown & recovery'),
  }
  const updateParams = (key: Exclude<keyof BacktestParams, 'average'>, value: string) => {
    setParams({ ...params, [key]: value === '' ? NaN : Number(value) })
    setDirty(true)
  }
  const loadCsv = (value: string, label: string) => {
    setCsv(value)
    setSource(label)
    setDirty(true)
    setError('')
  }
  const importFile = async (file?: File) => {
    if (!file) return
    try {
      if (file.size > 1024 * 1024) throw new Error(text('CSV 文件不能超过 1 MB', 'CSV files must not exceed 1 MB'))
      loadCsv(await file.text(), file.name)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    }
    if (fileInput.current) fileInput.current.value = ''
  }
  const calculate = () => {
    try {
      setRun({ result: backtest(parsePriceCsv(csv), params), source, data: csv })
      setDirty(false)
      setError('')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    }
  }
  const fields: { key: Exclude<keyof BacktestParams, 'average'>; label: string; min: number; max: number; step: number }[] = [
    { key: 'fast', label: text('短均线周期', 'Fast window'), min: 2, max: 249, step: 1 },
    { key: 'slow', label: text('长均线周期', 'Slow window'), min: 3, max: 250, step: 1 },
    { key: 'capital', label: text('初始资金', 'Initial capital'), min: 1, max: 1e9, step: 1 },
    { key: 'feeBps', label: text('单边手续费 · bps', 'Fee per side · bps'), min: 0, max: 100, step: 0.1 },
    { key: 'slippageBps', label: text('单边滑点 · bps', 'Slippage per side · bps'), min: 0, max: 100, step: 0.1 },
  ]
  const stats = [
    [text('策略累计收益', 'Strategy return'), percent(result.totalReturn)],
    [text('买入持有收益', 'Buy & hold return'), percent(result.benchmarkReturn)],
    [text('策略最大回撤', 'Maximum drawdown'), percent(result.maxDrawdown)],
    [text('成交笔数', 'Executions'), String(result.trades.length)],
  ]

  return (
    <div className="quant-page quant-lab">
      <Starfield />
      <div className="quant-lab-inner">
        <header className="quant-lab-head">
          <div><span className="quant-eyebrow"><FlaskConical size={14} />{text('本地研究实验室', 'LOCAL RESEARCH LAB')}</span>
            <h1>{text('量化金融', 'Quant Finance')}</h1>
            <p>{text('从一条可验证的策略开始。改参数、看曲线、检查每笔交易。', 'Change parameters, inspect equity, and audit each execution.')}</p></div>
          <span className="quant-local-badge">{text('本地计算 · 无 API 调用', 'LOCAL ONLY · NO API CALLS')}</span>
        </header>
        <details className="quant-guide"><summary>{text('怎么用：从示例到策略对照', 'How to use: from sample to comparison')}</summary>
          <ol>
            <li>{text('选择合成行情或导入 date,close CSV，确认数据口径；SMA 是简单均线，EMA 对近期价格更敏感。', 'Choose synthetic data or import a date,close CSV. SMA is a simple average; EMA weights recent prices more heavily.')}</li>
            <li>{text('设定周期与成本，点击运行；输入变化后，旧结果会标记为待重算。', 'Set windows and costs, then run. Edited inputs do not silently change the previous result.')}</li>
            <li>{text('固定本次为对照，再只改一个参数或均线类型并重新运行；数据与长周期保持一致。', 'Save the run for comparison, change one parameter or average type, and rerun with the same data and slow window.')}</li>
            <li>{text('切换净值/回撤并拖动日期滑条，核对成交记录，最后导出曲线或全部成交 CSV。', 'Inspect equity/drawdown with the date slider, audit executions, and export curve or complete ledger CSV.')}</li>
          </ol>
        </details>
        <div className="quant-lab-grid">
          <form className="quant-panel quant-controls" onSubmit={(event) => { event.preventDefault(); calculate() }}>
            <h2>{text('双均线 · 多头 / 空仓', 'Dual moving averages · Long / Cash')}</h2>
            <p>{text('短均线高于长均线时持有，否则空仓。', 'Hold when the fast average exceeds the slow average; otherwise hold cash.')}</p>
            <label className="quant-select-label">{text('均线类型', 'Average type')}
              <select value={params.average ?? 'sma'} onChange={(event) => {
                setParams({ ...params, average: event.target.value as AverageKind }); setDirty(true)
              }}>
                <option value="sma">{text('SMA · 简单均线', 'SMA · Simple average')}</option>
                <option value="ema">{text('EMA · 指数均线', 'EMA · Exponential average')}</option>
              </select>
            </label>
            <div className="quant-fields">{fields.map((field) => <label key={field.key}>{field.label}
              <input type="number" required value={Number.isNaN(params[field.key]) ? '' : params[field.key]}
                min={field.min} max={field.max} step={field.step}
                onChange={(event) => updateParams(field.key, event.target.value)} />
            </label>)}</div>
            <p className="quant-small">{text('1 bps = 0.01%；手续费与滑点合并为按成交额扣除的摩擦成本。', '1 bp = 0.01%. Fees and slippage are combined as a notional trading cost.')}</p>
            <label className="quant-select-label">{text('合成市场情景', 'Synthetic scenario')}
              <select value={scenario} onChange={(event) => {
                const next = event.target.value as MarketScenario
                setScenario(next); loadCsv(samplePriceCsv(next), `sample:${next}`)
              }}>
                {Object.entries(scenarioNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <div className="quant-data-actions">
              <button type="button" onClick={() => loadCsv(samplePriceCsv(scenario), `sample:${scenario}`)}>{text('重载示例', 'Reload sample')}</button>
              <button type="button" onClick={() => fileInput.current?.click()}><Upload size={14} />{text('导入 CSV', 'Import CSV')}</button>
              <button type="button" onClick={() => downloadCsv(samplePriceCsv(scenario), `synthetic-${scenario}.csv`)}><Download size={14} />{text('下载示例 CSV', 'Sample CSV')}</button>
              <input hidden ref={fileInput} type="file" accept=".csv,text/csv" aria-label={text('选择 CSV 文件', 'Select CSV file')}
                onChange={(event) => void importFile(event.target.files?.[0])} />
            </div>
            <details className="quant-data-editor"><summary>{text('查看 / 粘贴价格数据', 'View / paste price data')}</summary>
              <p className="quant-small">{text('两列 date,close；日期 YYYY-MM-DD，按日期升序；最多 5000 行。数据只留在当前页面。', 'Two columns: date,close. Ascending YYYY-MM-DD dates; up to 5000 rows. Data stays in this page.')}</p>
              <textarea aria-label={text('价格 CSV', 'Price CSV')} value={csv} rows={7} maxLength={1024 * 1024}
                onChange={(event) => loadCsv(event.target.value, 'custom')} spellCheck={false} />
            </details>
            <button className="quant-run" type="submit"><Play size={15} />{text('运行回测', 'Run backtest')}</button>
            {error && <p className="quant-error" role="alert">{error}</p>}
            {dirty && <p className="quant-pending" role="status">{text('输入已修改，下方仍为上次结果；请重新运行。', 'Inputs changed. Results show the previous run until you run again.')}</p>}
          </form>
          <div className="quant-results">
            <div className="quant-source-note" role="note">
              <strong>{run.source.startsWith('sample:') ? `${text('合成示例 · 非真实行情', 'SYNTHETIC SAMPLE · NOT MARKET DATA')} · ${scenarioNames[run.source.slice(7) as MarketScenario]}` : text('本地导入 · 未核验行情', 'LOCAL INPUT · UNVERIFIED DATA')}</strong>
              <span>{result.params.fast}/{result.params.slow} {(result.params.average ?? 'sma').toUpperCase()} · {result.points[0].date} → {result.points[result.points.length - 1].date}</span>
            </div>
            <div className="quant-stats">{stats.map(([label, value]) => <div className="quant-panel" key={label}>
              <span>{label}</span><strong>{value}</strong></div>)}</div>
            <section className="quant-panel">
              <div className="quant-section-head"><h2>{text('净值与风险', 'Equity & risk')}</h2>
                <div className="quant-result-actions"><button type="button" disabled={dirty} onClick={() => setReference(run)}>{text('固定本次为对照', 'Save for comparison')}</button>
                  <button type="button" onClick={() => downloadCsv(equityCsv(result), `fin-agent-${run.source.startsWith('sample:') ? 'synthetic' : 'local'}-equity.csv`)}>
                    <Download size={14} />{text('导出曲线 CSV', 'Export curve CSV')}</button></div></div>
              <EquityChart key={`${result.params.average}-${result.params.fast}-${result.params.slow}-${result.points.length}-${run.source}`} result={result} lang={lang} />
              <p className="quant-small">{text('期末资金', 'Ending equity')} {number(result.points[result.points.length - 1].equity)}
                {' · '}{text('策略摩擦成本', 'Strategy trading cost')} {number(result.totalCost)}
                {' · '}{text('金额单位与导入价格一致', 'Amounts use the input price unit')}</p>
            </section>
            {reference && <QuantComparison current={run} reference={reference} lang={lang} onClear={() => setReference(null)} />}
            <section className="quant-panel">
              <div className="quant-section-head"><h2>{text('成交记录', 'Execution ledger')}</h2>
                <button type="button" onClick={() => downloadCsv(tradesCsv(result), `fin-agent-${run.source.startsWith('sample:') ? 'synthetic' : 'local'}-trades.csv`)}><Download size={14} />{text('导出全部成交', 'Export all executions')}</button></div>
              <div className="quant-table-wrap"><table><thead><tr>{[
                text('成交日期', 'Execution date'), text('信号日期', 'Signal date'), text('方向', 'Side'),
                text('参考收盘价', 'Reference close'), text('数量', 'Quantity'), text('摩擦成本', 'Trading cost'),
              ].map((label) => <th key={label}>{label}</th>)}</tr></thead>
                <tbody>{result.trades.slice(-100).map((trade, i) => <tr key={i}>
                  <td>{trade.date}</td><td>{trade.signalDate}</td><td>{trade.side === 'buy' ? text('买入', 'Buy') : text('卖出', 'Sell')}</td>
                  <td>{number(trade.price)}</td><td>{number(trade.quantity)}</td><td>{number(trade.cost)}</td>
                </tr>)}</tbody></table></div>
              {!result.trades.length && <p>{text('本区间没有触发交易，策略持有现金。', 'No executions; the strategy held cash.')}</p>}
              {result.trades.length > 100 && <p>{text('仅展示最近 100 笔。', 'Showing the latest 100 executions.')}</p>}
            </section>
          </div>
        </div>
        <footer className="quant-assumptions"><strong>{text('回测假设与边界', 'Assumptions & limits')}</strong>
          <p>{text('前一条收盘数据生成信号，下一条收盘价模拟成交；预热结束后策略与买入持有基准从同一起点计量。只做多，允许小数份额，现金不计息；期末持仓按收盘价估值，不强制平仓。未模拟涨跌停、停牌、交易日历、最小佣金、税费与整手限制。真实分析需自行提供口径一致、正确复权的数据。', 'Signals use the previous close and execute at the next close. Strategy and benchmark share a post-warmup start. Long-only with fractional units, no cash interest, and open positions marked to market without forced liquidation. No limits, suspensions, exchange calendar, minimum fees, taxes, or lot restrictions. Supply consistently adjusted data for real analysis.')}</p>
          <p>{text('这是教学与工程验证雏形，不是投资建议或实盘交易系统；示例收益不能代表真实策略表现。', 'An educational engineering prototype, not investment advice or a live trading system. Synthetic returns do not represent real performance.')}</p>
        </footer>
      </div>
    </div>
  )
}
