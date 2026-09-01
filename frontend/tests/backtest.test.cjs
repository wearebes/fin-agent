const assert = require('node:assert/strict')
const { test } = require('node:test')
const path = require('node:path')
const { buildSync } = require('esbuild')

const code = buildSync({
  entryPoints: [path.join(__dirname, '../src/lib/backtest.ts')], bundle: true,
  platform: 'node', format: 'cjs', write: false,
}).outputFiles[0].text
const compiled = { exports: {} }
new Function('module', 'exports', code)(compiled, compiled.exports)
const { backtest, parsePriceCsv, samplePriceCsv, equityCsv, tradesCsv, comparablePeriods, DEFAULT_PARAMS } = compiled.exports
const params = { fast: 2, slow: 3, capital: 1000, feeBps: 0, slippageBps: 0 }
const bars = (prices) => prices.map((close, i) => ({ date: new Date(Date.UTC(2024, 0, i + 1)).toISOString().slice(0, 10), close }))
const near = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-9, `${actual} != ${expected}`)

test('signal trades at the following close, not at the price used by the signal', () => {
  const result = backtest(bars([1, 2, 3, 30, 60]), params)
  assert.equal(result.trades[0].date, '2024-01-04')
  assert.equal(result.trades[0].signalDate, '2024-01-03')
  assert.equal(result.trades[0].price, 30)
  near(result.points[1].equity, 1000)
  near(result.totalReturn, 1)
  near(result.benchmarkReturn, 1)
})

test('future prices cannot change earlier trades or equity', () => {
  for (const average of ['sma', 'ema']) {
    const first = backtest(bars([10, 11, 12, 13, 14, 15, 20, 25]), { ...params, average })
    const second = backtest(bars([10, 11, 12, 13, 14, 15, 2, 1]), { ...params, average })
    assert.deepEqual(first.points.slice(0, 4), second.points.slice(0, 4))
    assert.deepEqual(first.trades.filter((t) => t.date < '2024-01-07'), second.trades.filter((t) => t.date < '2024-01-07'))
  }
})

test('entry and exit costs reconcile to cash and no negative cash or fractional-value loss', () => {
  const result = backtest(bars([10, 11, 12, 13, 9, 8, 7]), { ...params, feeBps: 100 })
  const quantity = 1000 / (13 * 1.01)
  const exitCash = quantity * 8 * 0.99
  assert.deepEqual(result.trades.map((t) => t.side), ['buy', 'sell'])
  near(result.points.at(-1).equity, exitCash)
  near(result.totalCost, quantity * 13 * 0.01 + quantity * 8 * 0.01)
  near(result.maxDrawdown, exitCash / 1000 - 1)
  assert.equal(result.points.at(-1).position, 0)
})

test('constant decimal prices produce no strategy trades and zero return', () => {
  const result = backtest(bars(Array(20).fill(100.1)), { ...params, fast: 3, slow: 7, feeBps: 10 })
  assert.equal(result.trades.length, 0)
  near(result.totalReturn, 0)
  near(result.maxDrawdown, 0)
  assert.ok(result.benchmarkReturn < 0)
  for (const close of [0.1, 100.1, 123.456789]) {
    for (const average of ['sma', 'ema']) {
      for (const fast of [2, 3, 10]) {
        for (const slow of [11, 20, 30]) {
          assert.equal(backtest(bars(Array(50).fill(close)), { ...params, fast, slow, average }).trades.length, 0)
        }
      }
    }
  }
})

test('CSV accepts BOM, CRLF and quoted scalar cells, preserving precision', () => {
  const result = parsePriceCsv('\uFEFF"date","close"\r\n"2024-01-01","12.123456"\r\n2024-01-02,13\r\n')
  assert.equal(result[0].close, 12.123456)
})

test('CSV rejects invalid or duplicate dates, non-numeric prices, missing and extra fields', () => {
  for (const invalid of ['2024-02-30,10', '2024-01-01,Infinity', '2024-01-01,12oops',
    '2024-01-01,0', '2024-01-01,-1', '2024-01-01,2,3', '2024-01-02,10']) {
    assert.throws(() => parsePriceCsv(`date,close\n${invalid}\n2024-01-02,12`))
  }
  assert.throws(() => parsePriceCsv('date,close\n2024-01-02,10\n2024-01-01,12'))
})

test('invalid windows, costs, capital and insufficient history fail before calculation', () => {
  for (const patch of [{ fast: 3 }, { fast: 1.5 }, { slow: 251 }, { feeBps: -1 },
    { slippageBps: NaN }, { capital: 0 }, { capital: Infinity }, { slow: 20 }, { average: 'unknown' }]) {
    assert.throws(() => backtest(bars([1, 2, 3, 4, 5]), { ...params, ...patch }))
  }
  assert.throws(() => backtest(bars([1e308, 1e308, 1e308, 1e308, 1e308]), params), /precision|numeric/)
  assert.throws(() => backtest(bars(Array(5001).fill(100)), params), /5000/)
})

test('synthetic demo is deterministic; export values reconcile exactly with plotted equity', () => {
  assert.equal(samplePriceCsv(), samplePriceCsv())
  const prices = parsePriceCsv(samplePriceCsv())
  const result = backtest(prices, DEFAULT_PARAMS)
  assert.equal(prices.length, 300)
  assert.ok(result.trades.length > 0)
  const exported = equityCsv(result).split('\n').at(-1).split(',')
  near(Number(exported[2]), result.points.at(-1).equity)
  near(result.totalReturn, Number(exported[2]) / DEFAULT_PARAMS.capital - 1)
  assert.deepEqual(result.params, DEFAULT_PARAMS)
})

test('EMA uses an SMA seed and subsequent exponential weights, retaining next-close execution', () => {
  const data = bars([1, 2, 3, 2, 2, 5, 1])
  const sma = backtest(data, params)
  const ema = backtest(data, { ...params, average: 'ema' })
  assert.deepEqual(ema.trades.map((t) => [t.date, t.side]), [['2024-01-04', 'buy']])
  near(ema.points.at(-1).equity, 500)
  assert.deepEqual(sma.trades.map((t) => t.side), ['buy', 'sell', 'buy'])
  near(sma.points.at(-1).equity, 2500)
})

test('benchmark drawdown tracks its own peak and returns to zero on recovery', () => {
  const result = backtest(bars([1, 2, 3, 4, 2, 4, 8]), params)
  assert.deepEqual(result.points.map((p) => p.benchmarkDrawdown), [0, 0, -0.5, 0, 0])
  near(result.maxDrawdown, Math.min(...result.points.map((p) => p.drawdown)))
})

test('comparison rejects changed evaluation period, prices or capital', () => {
  const data = bars([1, 2, 3, 4, 2, 4, 8])
  const original = backtest(data, params)
  assert.equal(comparablePeriods(original, backtest(data, { ...params, average: 'ema' })), true)
  assert.equal(comparablePeriods(original, backtest(data, { ...params, slow: 4 })), false)
  assert.equal(comparablePeriods(original, backtest(data, { ...params, capital: 2000 })), false)
  assert.equal(comparablePeriods(original, backtest(bars([1, 2, 3, 4, 2, 4, 9]), params)), false)
})

test('three distinct synthetic regimes validate and the complete trade ledger exports without rounding', () => {
  const samples = ['cycle', 'trend', 'drawdown'].map((scenario) => samplePriceCsv(scenario))
  assert.equal(new Set(samples).size, 3)
  for (const csv of samples) {
    const prices = parsePriceCsv(csv)
    assert.equal(prices.length, 300)
    const result = backtest(prices, DEFAULT_PARAMS)
    const rows = tradesCsv(result).split('\n')
    assert.equal(rows.length, result.trades.length + 1)
    result.trades.forEach((trade, i) => near(Number(rows[i + 1].split(',')[5]), trade.cost))
  }
})
