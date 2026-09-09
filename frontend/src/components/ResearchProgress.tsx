import { useEffect, useState } from 'react'
import { translate } from '../i18n'
import type { Lang, ResearchProgress as Progress } from '../types'

export default function ResearchProgress({ progress, startedAt, lang }: {
  progress?: Progress; startedAt: number; lang: Lang
}) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])
  return (
    <div className="live-progress" role="status">
      <div className="status-pill running"><span className="spinner" />
        {translate(lang, 'running')} · {Math.max(0, Math.floor((now - startedAt) / 1000))}s
      </div>
      <p>{progress
        ? `${translate(lang, `stage_${progress.stage}`)} · ${translate(lang, `stageStatus_${progress.status}`)}`
        : translate(lang, 'awaitingProgress')}
      </p>
      <small>{translate(lang, 'progressNotice')}</small>
    </div>
  )
}
