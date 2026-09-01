export interface PriceBar { date: string; close: number }
export type AverageKind = 'sma' | 'ema'
export type MarketScenario = 'cycle' | 'trend' | 'drawdown'
export interface BacktestParams {
  fast: number; slow: number; capital: number; feeBps: number; slippageBps: number
  average?: AverageKind
}
export interface EquityPoint extends PriceBar {
  equity: number; benchmark: number; drawdown: number; position: number
  benchmarkDrawdown: number
}
export interface Trade {
  date: string; signalDate: string; side: 'buy' | 'sell'; price: number; quantity: number; cost: number
}
export interface BacktestResult {
  params: BacktestParams; points: EquityPoint[]; trades: Trade[]
  totalReturn: number; benchmarkReturn: number; maxDrawdown: number; totalCost: number
}

export const DEFAULT_PARAMS: BacktestParams = {
  fast: 10, slow: 30, capital: 100000, feeBps: 3, slippageBps: 5, average: 'sma',
}
export const MAX_ROWS = 5000

function validDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const time = Date.parse(`${value}T00:00:00Z`)
  return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === value
}

function validateBars(bars: PriceBar[]): void {
  if (bars.length < 2 || bars.length > MAX_ROWS) throw new Error('数据需为 2–5000 行 / Use 2–5000 rows')
  bars.forEach((bar, index) => {
    if (!validDate(bar.date) || !Number.isFinite(bar.close) || bar.close <= 0) {
      throw new Error(`第 ${index + 1} 行日期或价格无效 / Invalid date or price in row ${index + 1}`)
    }
    if (index && bar.date <= bars[index - 1].date) {
      throw new Error('日期必须升序且不能重复 / Dates must be ascending and unique')
    }
  })
}

export function parsePriceCsv(text: string): PriceBar[] {
  const lines = text.replace(/^\uFEFF/, '').trim().split(/\r?\n/)
  const cells = (line: string) => line.split(',').map((cell) => cell.trim().replace(/^"([^"]*)"$/, '$1'))
  if (cells(lines[0] ?? '').join(',').toLowerCase() !== 'date,close') {
    throw new Error('CSV 表头必须为 date,close / CSV header must be date,close')
  }
  const bars = lines.slice(1).map((line, index) => {
    const values = cells(line)
    if (values.length !== 2 || !/^(?:\d+\.?\d*|\.\d+)$/.test(values[1])) {
      throw new Error(`CSV 第 ${index + 2} 行格式错误 / Invalid CSV row ${index + 2}`)
    }
    return { date: values[0], close: Number(values[1]) }
  })
  validateBars(bars)
  return bars
}

function movingAverage(bars: PriceBar[], period: number, kind: AverageKind): (number | null)[] {
  let sum = 0
  let previous: number | null = null
  return bars.map((bar, index) => {
    if (kind === 'ema' && previous !== null) {
      previous += (bar.close - previous) * 2 / (period + 1)
      return previous
    }
    sum += bar.close
    if (!Number.isFinite(sum)) throw new Error('价格超出计算精度范围 / Prices exceed numeric limits')
    if (index >= period) sum -= bars[index - period].close
    if (index < period - 1) return null
    previous = sum / period
    return previous
  })
}

export function backtest(bars: PriceBar[], params: BacktestParams): BacktestResult {
  validateBars(bars)
  const { fast, slow, capital, feeBps, slippageBps, average = 'sma' } = params
  if (!['sma', 'ema'].includes(average)) throw new Error('不支持的均线类型 / Unsupported average type')
  if (!Number.isInteger(fast) || !Number.isInteger(slow) || fast < 2 || fast >= slow || slow > 250) {
    throw new Error('周期需满足 2 ≤ 短周期 < 长周期 ≤ 250 / Invalid moving-average periods')
  }
  if (!Number.isFinite(capital) || capital < 1 || capital > 1e9) {
    throw new Error('初始资金范围为 1–10 亿 / Capital must be between 1 and 1 billion')
  }
  if ([feeBps, slippageBps].some((value) => !Number.isFinite(value) || value < 0 || value > 100)) {
    throw new Error('手续费和滑点各需为 0–100 bps / Costs must be 0–100 bps each')
  }
  if (bars.length < slow + 2) throw new Error('数据不足，至少需要长周期 + 2 行 / Not enough rows')

  const fastMA = movingAverage(bars, fast, average)
  const slowMA = movingAverage(bars, slow, average)
  const friction = (feeBps + slippageBps) / 10000
  const benchmarkShares = capital / (bars[slow].close * (1 + friction))
  let cash = capital
  let shares = 0
  let peak = capital
  let benchmarkPeak = capital
  let maxDrawdown = 0
  let totalCost = 0
  const trades: Trade[] = []
  const points: EquityPoint[] = [{
    ...bars[slow - 1], equity: capital, benchmark: capital, drawdown: 0, position: 0, benchmarkDrawdown: 0,
  }]

  for (let i = slow; i < bars.length; i++) {
    const bar = bars[i]
    // Yesterday's completed signal trades at today's close, never at yesterday's price.
    const fastValue = fastMA[i - 1]!
    const slowValue = slowMA[i - 1]!
    // Equal averages must not create trades from floating-point summation noise.
    const tolerance = Number.EPSILON * slow * Math.max(fastValue, slowValue)
    const wantLong = fastValue - slowValue > tolerance
    if (wantLong !== (shares > 0)) {
      const before = cash + shares * bar.close
      const quantity = wantLong ? cash / (bar.close * (1 + friction)) : shares
      if (wantLong) {
        shares = quantity
        cash = 0
      } else {
        cash = quantity * bar.close * (1 - friction)
        shares = 0
      }
      const cost = Math.max(0, before - cash - shares * bar.close)
      totalCost += cost
      trades.push({ date: bar.date, signalDate: bars[i - 1].date,
        side: wantLong ? 'buy' : 'sell', price: bar.close, quantity, cost })
    }
    const equity = cash + shares * bar.close
    const benchmark = benchmarkShares * bar.close
    if (![equity, benchmark, shares].every(Number.isFinite)) {
      throw new Error('价格数值过于极端，无法可靠计算 / Price range exceeds numeric limits')
    }
    peak = Math.max(peak, equity)
    benchmarkPeak = Math.max(benchmarkPeak, benchmark)
    const drawdown = equity / peak - 1
    maxDrawdown = Math.min(maxDrawdown, drawdown)
    points.push({ ...bar, equity, benchmark, drawdown, position: shares, benchmarkDrawdown: benchmark / benchmarkPeak - 1 })
  }
  const last = points[points.length - 1]
  return { params: { ...params, average }, points, trades, totalCost, maxDrawdown,
    totalReturn: last.equity / capital - 1, benchmarkReturn: last.benchmark / capital - 1 }
}

export function samplePriceCsv(scenario: MarketScenario = 'cycle'): string {
  const rows = ['date,close']
  const day = new Date('2024-01-02T00:00:00Z')
  for (let i = 0; i < 300; day.setUTCDate(day.getUTCDate() + 1)) {
    if ([0, 6].includes(day.getUTCDay())) continue
    const trend = scenario === 'trend' ? 0.0012 * i + 0.018 * Math.sin(i / 10)
      : scenario === 'drawdown' ? 0.0006 * i - 0.45 * Math.exp(-(((i - 160) / 23) ** 2))
      : 0.0004 * i + 0.1 * Math.sin(i / 22)
    const close = 100 * Math.exp(trend + 0.025 * Math.sin(i / 3.7))
    rows.push(`${day.toISOString().slice(0, 10)},${close.toFixed(4)}`)
    i++
  }
  return rows.join('\n')
}

export function equityCsv(result: BacktestResult): string {
  return ['date,close,strategy_equity,benchmark_equity,drawdown,position,benchmark_drawdown',
    ...result.points.map((p) => [p.date, p.close, p.equity, p.benchmark, p.drawdown, p.position, p.benchmarkDrawdown].join(',')),
  ].join('\n')
}

export function tradesCsv(result: BacktestResult): string {
  return ['date,signal_date,side,reference_close,quantity,trading_cost',
    ...result.trades.map((t) => [t.date, t.signalDate, t.side, t.price, t.quantity, t.cost].join(',')),
  ].join('\n')
}

export function comparablePeriods(left: BacktestResult, right: BacktestResult): boolean {
  return left.params.capital === right.params.capital && left.points.length === right.points.length
    && left.points.every((point, i) => point.date === right.points[i].date && point.close === right.points[i].close)
}
