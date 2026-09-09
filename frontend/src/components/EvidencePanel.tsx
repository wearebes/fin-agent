import { ExternalLink } from 'lucide-react'
import { translate } from '../i18n'
import { safeSourceUrl } from '../lib/research'
import type { EvidenceItem, Lang } from '../types'

const labels: Record<string, string> = {
  total_revenue: '营业收入', net_income: '净利润', total_assets: '总资产',
  total_liabilities: '总负债', total_equity: '股东权益', operating_cash_flow: '经营现金流',
  net_operating_cash_flow: '经营活动现金流净额', free_cash_flow: '自由现金流',
  revenue_yoy: '收入同比', net_profit_margin: '净利率', currency: '币种', unit: '单位',
  premium_income: '保费收入', inventory_turnover_days: '存货周转天数',
  solvency_adequacy_ratio: '偿付能力充足率',
}

type RecordData = Record<string, unknown>
const isRecord = (value: unknown): value is RecordData =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

function readRecords(summary: string): { rows: RecordData[]; omitted: number } {
  try {
    const parsed: unknown = JSON.parse(summary)
    const data = Array.isArray(parsed) ? parsed : isRecord(parsed) ? parsed.records ?? [parsed] : []
    return {
      rows: Array.isArray(data) ? data.filter(isRecord) : [],
      omitted: isRecord(parsed) && typeof parsed.omitted_records === 'number'
        ? parsed.omitted_records : 0,
    }
  } catch {
    return { rows: [], omitted: 0 }
  }
}

function EvidenceCard({ item, index, lang }: { item: EvidenceItem; index: number; lang: Lang }) {
  const { rows, omitted } = readRecords(item.summary)
  const financials = rows.length > 0 && rows.every((row) => typeof row.fiscal_year === 'number')
  const metrics = financials ? [...new Set(rows.flatMap(Object.keys))].filter((key) =>
    !['ticker', 'statement_type', 'fiscal_year', 'fiscal_quarter'].includes(key),
  ) : []
  const markdownLink = item.summary.match(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/)
  const links = rows.flatMap((row) => {
    const url = safeSourceUrl(row.url)
    return url ? [{ url, title: String(row.title ?? row.name ?? new URL(url).hostname) }] : []
  })
  const sourceUrl = safeSourceUrl(markdownLink?.[2] ?? item.source)
  if (sourceUrl) links.unshift({ url: sourceUrl, title: markdownLink?.[1] ?? new URL(sourceUrl).hostname })
  const uniqueLinks = links.filter((link, position) => links.findIndex((x) => x.url === link.url) === position)

  return (
    <article className="evidence-card">
      <div className="evidence-source"><span className="source-number">{index + 1}</span>{item.source}</div>
      {uniqueLinks.map(({ url, title }) => (
        <a className="source-link" href={url} target="_blank" rel="noopener noreferrer" key={url}>
          <span>{title}<small>{new URL(url).hostname}</small></span><ExternalLink size={14} />
        </a>
      ))}
      {financials && (
        <>
          <div className="evidence-table-wrap" tabIndex={0} aria-label={item.source}>
            <table className="evidence-table">
              <thead><tr><th>{translate(lang, 'metric')}</th>{rows.map((row, i) =>
                <th key={i}>{String(row.ticker ?? '')}<br />{String(row.fiscal_year)}
                  {row.fiscal_quarter != null ? ` Q${row.fiscal_quarter}` : ' FY'}</th>,
              )}</tr></thead>
              <tbody>{metrics.map((key) => <tr key={key}>
                <th>{lang === 'zh' ? labels[key] ?? key : key.replace(/_/g, ' ')}</th>
                {rows.map((row, i) => <td key={i}>{row[key] == null ? '—' : String(row[key])}</td>)}
              </tr>)}</tbody>
            </table>
          </div>
          <p className="source-note">{translate(lang, 'sourceUnits')}</p>
        </>
      )}
      {!financials && rows.length === 0 && <p className="evidence-text">{item.summary}</p>}
      {omitted > 0 && <p className="source-note">{omitted} {translate(lang, 'evidenceOmitted')}</p>}
      <details className="raw-evidence"><summary>{translate(lang, 'rawEvidence')}</summary>
        <pre>{item.summary}</pre>
      </details>
    </article>
  )
}

export default function EvidencePanel({ evidence, lang }: { evidence: EvidenceItem[]; lang: Lang }) {
  if (!evidence.length) return <p className="source-note">{translate(lang, 'noEvidence')}</p>
  return <div className="evidence-list">{evidence.map((item, index) =>
    <EvidenceCard key={`${item.source}-${index}`} item={item} index={index} lang={lang} />,
  )}</div>
}
