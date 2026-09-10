import { useState, type ReactNode } from 'react'
import type { ReportChart, ReportData } from '../types'

const colors = ['#2563eb', '#475569', '#0f766e', '#b7791f']
const number = (value: number) => new Intl.NumberFormat(undefined, {
  notation: Math.abs(value) >= 1000000 ? 'compact' : 'standard', maximumFractionDigits: 2,
}).format(value)

function Figure({ chart, en }: { chart: ReportChart; en: boolean }) {
  const [hover, setHover] = useState<number | null>(null)
  const values = chart.series.flatMap((s) => s.values).filter((v): v is number => v !== null && Number.isFinite(v))
  if (!values.length || !chart.labels.length) return null
  const low = Math.min(...values, ...(chart.kind === 'bar' ? [0] : []))
  const high = Math.max(...values, ...(chart.kind === 'bar' ? [0] : []))
  const padding = (high - low || Math.abs(high) || 1) * .08
  const min = low - padding, max = high + padding
  const x = (i: number) => 76 + (i + .5) / chart.labels.length * 550
  const y = (v: number) => 215 - (v - min) / (max - min) * 185
  const barWidth = Math.min(36, 440 / chart.labels.length / chart.series.length)
  const ticks = [...new Set([0, Math.floor((chart.labels.length - 1) / 2), chart.labels.length - 1])]
  return <figure className="research-figure">
    <figcaption><h3>{chart.title}</h3><p>{chart.unit} · {chart.note}</p></figcaption>
    <div className="research-figure-legend">{chart.series.map((s, i) => <span key={s.name}>
      <i style={{ background: colors[i % colors.length] }} />{s.name}</span>)}</div>
    <svg viewBox="0 0 680 255" role="img" aria-label={`${chart.title} (${chart.unit})`}
      onPointerLeave={() => setHover(null)} onPointerMove={(e) => {
        const bounds = e.currentTarget.getBoundingClientRect()
        setHover(Math.max(0, Math.min(chart.labels.length - 1,
          Math.floor(((e.clientX - bounds.left) / bounds.width * 680 - 76) / 550 * chart.labels.length))))
      }}>
      {[0, 1, 2, 3, 4].map((i) => { const v = min + (max - min) * i / 4; return <g key={i}>
        <line x1="76" x2="626" y1={y(v)} y2={y(v)} stroke="#e2e8f0" />
        <text x="68" y={y(v) + 4} textAnchor="end">{number(v)}</text>
      </g> })}
      {low <= 0 && high >= 0 && <line x1="76" x2="626" y1={y(0)} y2={y(0)} stroke="#94a3b8" />}
      {ticks.map((i) => <text key={i} x={x(i)} y="242" textAnchor="middle">{chart.labels[i]}</text>)}
      {chart.series.map((series, si) => chart.kind === 'bar'
        ? <g key={series.name}>{series.values.map((v, i) => v !== null && Number.isFinite(v) &&
          <rect key={i} x={x(i) + (si - chart.series.length / 2) * barWidth} y={Math.min(y(v), y(0))}
            width={barWidth - 2} height={Math.max(1, Math.abs(y(v) - y(0)))} fill={colors[si % colors.length]}>
            <title>{`${chart.labels[i]} · ${series.name}: ${number(v)} ${chart.unit}`}</title></rect>)}</g>
        : <path key={series.name} fill="none" stroke={colors[si % colors.length]} strokeWidth="2"
          strokeDasharray={si % 2 ? '6 3' : undefined} d={series.values.map((v, i) =>
            v === null || !Number.isFinite(v) ? '' : `${i === 0 || series.values[i - 1] === null ? 'M' : 'L'}${x(i)},${y(v)}`).join(' ')} />)}
      {hover !== null && <line x1={x(hover)} x2={x(hover)} y1="28" y2="215" stroke="#64748b" strokeDasharray="3 3" />}
    </svg>
    <div className="research-figure-values" aria-live="polite">{hover !== null ? <>
      <b>{chart.labels[hover]}</b>{chart.series.map((s) => <span key={s.name}>{s.name}: {s.values[hover] == null ? '—' : number(s.values[hover]!)} {chart.unit}</span>)}
    </> : <span>{en ? 'Hover to inspect; exact values below.' : '悬停查看日期和数值，也可展开下方数据表。'}</span>}</div>
    <p className="research-figure-source">{en ? 'Source: ' : '来源：'}{chart.source}</p>
    <details><summary>{en ? 'Source observations' : '查看原始观测值'}</summary><div className="research-data-table"><table>
      <thead><tr><th>{en ? 'Date / period' : '日期 / 期间'}</th>{chart.series.map((s) => <th key={s.name}>{s.name} ({chart.unit})</th>)}</tr></thead>
      <tbody>{chart.labels.map((label, i) => <tr key={`${label}-${i}`}><td>{label}</td>{chart.series.map((s) => <td key={s.name}>{s.values[i] ?? '—'}</td>)}</tr>)}</tbody>
    </table></div></details>
  </figure>
}

export default function ReportFigures({ data, en, children }: { data: ReportData; en: boolean; children?: ReactNode }) {
  return <div className="research-figures">
    <div className="research-report-meta"><b>{data.narrative === 'ai' ? (en ? 'AI narrative · data-backed figures' : 'AI 撰写 · 数据图表') : (en ? 'Data summary · AI report unavailable' : '数据摘要 · AI 研报未完成')}</b>
      <span>{en ? 'Captured ' : '取数时间 '}{new Date(data.captured_at).toLocaleString()}</span></div>
    <div className="research-metrics">{data.metrics.map((metric) => <article key={metric.label}>
      <span>{metric.label}</span><strong>{number(metric.value)}<small>{metric.unit}</small></strong><p>{metric.context}</p>
    </article>)}</div>
    {data.summary.length > 0 && <div className="research-data-summary"><h3>{en ? 'Data highlights' : '数据要点'}</h3>{data.summary.map((s) => <p key={s}>{s}</p>)}</div>}
    {children}
    {data.charts.map((chart, i) => <Figure key={`${chart.title}-${i}`} chart={chart} en={en} />)}
    {data.gaps.length > 0 && <details className="research-data-gaps" open><summary>{en ? 'Data coverage' : '数据覆盖说明'}</summary>{data.gaps.map((gap) => <p key={gap}>{gap}</p>)}</details>}
  </div>
}
