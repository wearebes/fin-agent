import { useEffect, useState } from 'react'
import { translate } from '../i18n'
import type { Lang, ResearchProgress as Progress } from '../types'
import { jobStage } from '../api/jobs'

export default function ResearchProgress({ progress, startedAt, lang, background = false }: {
  progress?: Progress; startedAt: number; lang: Lang; background?: boolean
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
        ? `${background ? jobStage(progress.stage, lang === 'en') : translate(lang, `stage_${progress.stage}`)} · ${translate(lang, `stageStatus_${progress.status}`)}`
        : translate(lang, 'awaitingProgress')}
      </p>
      <small>{background ? (lang === 'zh' ? '正在本机后台执行，可关闭页面并稍后从研究任务中心查看。' : 'Running on your local service. You can close this page and return later.') : translate(lang, 'progressNotice')}</small>
    </div>
  )
}
