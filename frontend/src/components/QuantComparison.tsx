import { comparablePeriods } from '../lib/backtest'
import type { BacktestResult } from '../lib/backtest'
import type { Lang } from '../types'

export interface QuantRun { result: BacktestResult; source: string; data: string }

export default function QuantComparison({ current, reference, lang, onClear }: {
  current: QuantRun; reference: QuantRun; lang: Lang; onClear: () => void
}) {
  const zh = lang === 'zh'
  const comparable = current.data === reference.data && comparablePeriods(current.result, reference.result)
  const label = ({ params }: BacktestResult) => `${(params.average ?? 'sma').toUpperCase()} ${params.fast}/${params.slow} · ${params.feeBps + params.slippageBps} bps`
  const metrics = [
    { label: zh ? '累计收益' : 'Return', key: 'totalReturn' as const, percent: true },
    { label: zh ? '最大回撤' : 'Max drawdown', key: 'maxDrawdown' as const, percent: true },
    { label: zh ? '摩擦成本' : 'Trading cost', key: 'totalCost' as const, percent: false },
  ]
  const format = (value: number, percent: boolean) => percent ? `${(value * 100).toFixed(2)}%` : value.toFixed(2)
  return (
    <section className="quant-panel">
      <div className="quant-section-head"><h2>{zh ? '两次回测对照' : 'Compare two runs'}</h2>
        <button type="button" onClick={onClear}>{zh ? '清除对照' : 'Clear comparison'}</button></div>
      <p className="quant-small">{zh ? '已固定' : 'Saved'} {label(reference.result)} → {zh ? '本次' : 'Current'} {label(current.result)}</p>
      {!comparable && <p className="quant-pending" role="note">{zh
        ? '数据、评估区间或初始资金不同，差值不具可比性；请保持数据、长周期与初始资金一致后重新运行。'
        : 'Data, evaluation period or capital differ. Keep the data, slow window and initial capital unchanged for a comparable difference.'}</p>}
      <div className="quant-table-wrap"><table><thead><tr>
        {[zh ? '指标' : 'Metric', zh ? '固定对照' : 'Saved', zh ? '本次结果' : 'Current', zh ? '变化' : 'Difference'].map((title) => <th key={title}>{title}</th>)}
      </tr></thead><tbody>{metrics.map(({ label: name, key, percent }) => {
        const before = reference.result[key]
        const after = current.result[key]
        return <tr key={key}><th>{name}</th><td>{format(before, percent)}</td><td>{format(after, percent)}</td>
          <td>{comparable ? `${((after - before) * (percent ? 100 : 1)).toFixed(2)}${percent ? (zh ? ' 个百分点' : ' pp') : ''}` : '—'}</td></tr>
      })}</tbody></table></div>
      <p className="quant-small">{zh ? '仅对照本区间结果，不代表样本外表现。修改参数后需重新运行；刷新或离开页面会清除对照。' : 'This comparison is in-sample only. Rerun after edits; leaving or refreshing the page clears the saved run.'}</p>
    </section>
  )
}
