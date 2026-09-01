import { useState } from 'react'
import type { BacktestResult } from '../lib/backtest'
import type { Lang } from '../types'

export default function EquityChart({ result, lang }: { result: BacktestResult; lang: Lang }) {
  const [selected, setSelected] = useState<number | null>(null)
  const [mode, setMode] = useState<'equity' | 'drawdown'>('equity')
  const { points, params } = result
  const zh = lang === 'zh'
  const valueOf = (index: number, benchmark = false) => mode === 'equity'
    ? points[index][benchmark ? 'benchmark' : 'equity'] / params.capital
    : points[index][benchmark ? 'benchmarkDrawdown' : 'drawdown'] * 100
  const values = points.flatMap((_, i) => [valueOf(i), valueOf(i, true)])
  const low = Math.min(...values)
  const high = Math.max(...values)
  const padding = Math.max((high - low) * 0.12, mode === 'equity' ? 0.01 : 0.5)
  const min = low - padding
  const max = mode === 'drawdown' ? 0 : high + padding
  const x = (i: number) => 58 + i / (points.length - 1) * 784
  const y = (value: number) => 22 + (max - value) / (max - min) * 220
  const path = (benchmark = false) => points.map((_, i) =>
    `${i ? 'L' : 'M'}${x(i).toFixed(2)},${y(valueOf(i, benchmark)).toFixed(2)}`,
  ).join(' ')
  const index = Math.min(selected ?? points.length - 1, points.length - 1)
  const point = points[index]

  return (
    <div className="equity-chart">
      <div className="quant-section-head">
        <div className="quant-legend"><span>{zh ? '策略' : 'Strategy'}</span>
          <span>{zh ? '买入持有' : 'Buy & hold'}</span></div>
        <div className="quant-chart-mode">
          <button type="button" aria-pressed={mode === 'equity'} onClick={() => setMode('equity')}>{zh ? '净值' : 'Equity'}</button>
          <button type="button" aria-pressed={mode === 'drawdown'} onClick={() => setMode('drawdown')}>{zh ? '回撤' : 'Drawdown'}</button>
        </div>
      </div>
      <svg viewBox="0 0 870 278" role="img" aria-label={mode === 'equity'
        ? (zh ? '策略与买入持有净值曲线' : 'Strategy and benchmark equity curves')
        : (zh ? '策略与买入持有回撤曲线' : 'Strategy and benchmark drawdown curves')}>
        {[0, 1, 2, 3, 4].map((tick) => {
          const value = min + (max - min) * tick / 4
          return <g key={tick}><line x1={58} x2={842} y1={y(value)} y2={y(value)} className="chart-grid" />
            <text x={48} y={y(value) + 4} textAnchor="end">{value.toFixed(mode === 'equity' ? 2 : 1)}{mode === 'drawdown' ? '%' : ''}</text></g>
        })}
        <path d={path(true)} className="chart-benchmark" />
        <path d={path()} className="chart-strategy" />
        <line x1={x(index)} x2={x(index)} y1={22} y2={242} className="chart-cursor" />
        <circle cx={x(index)} cy={y(valueOf(index))} r={4} fill="#64e9c3" />
        <text x={58} y={269}>{points[0].date}</text>
        <text x={842} y={269} textAnchor="end">{points[points.length - 1].date}</text>
      </svg>
      <label className="chart-scrubber">
        <span>{point.date} · {zh ? '策略' : 'Strategy'} {valueOf(index).toFixed(mode === 'equity' ? 4 : 2)}{mode === 'drawdown' ? '%' : ''}
          {' · '}{zh ? '基准' : 'Benchmark'} {valueOf(index, true).toFixed(mode === 'equity' ? 4 : 2)}{mode === 'drawdown' ? '%' : ''}
          {mode === 'equity' && <> · {zh ? '回撤' : 'Drawdown'} {(point.drawdown * 100).toFixed(2)}%</>}</span>
        <input type="range" min={0} max={points.length - 1} value={index}
          aria-label={zh ? '查看曲线日期' : 'Inspect curve date'}
          onChange={(event) => setSelected(Number(event.target.value))} />
      </label>
    </div>
  )
}
