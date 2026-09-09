import { ArrowUpRight } from 'lucide-react'
import { translate } from '../i18n'
import type { Lang } from '../types'

const examples = [
  { id: 'byd', ticker: '002594.SZ' },
  { id: 'tencent', ticker: '' },
  { id: 'liquor', ticker: '' },
  { id: 'bank', ticker: '600036.SH' },
  { id: 'nvidia', ticker: 'NVDA' },
  { id: 'gold', ticker: '' },
]

export default function ResearchExamples({ lang, onSelect }: {
  lang: Lang
  onSelect: (draft: { question: string; ticker: string }) => void
}) {
  return (
    <div className="example-questions">
      {examples.map(({ id, ticker }) => (
        <button className="example-question" key={id} type="button"
          title={translate(lang, `example_${id}_question`)} onClick={() =>
            onSelect({ question: translate(lang, `example_${id}_question`), ticker })
          }>
          <span>{translate(lang, `example_${id}`)}</span><ArrowUpRight size={14} aria-hidden="true" />
        </button>
      ))}
    </div>
  )
}
