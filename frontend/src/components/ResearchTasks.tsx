import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getJob, jobStage, listJobs, submitJob } from '../api/jobs'
import { useUserStore } from '../store/user'
import { useWorkspace } from '../store/workspace'
import AssistantResult from './AssistantResult'

export default function ResearchTasks() {
  const { jobId } = useParams()
  const navigate = useNavigate()
  const en = useWorkspace((s) => s.lang === 'en')
  const token = useUserStore((s) => s.token)
  const [offset, setOffset] = useState(0)
  const [retrying, setRetrying] = useState(false)
  const [error, setError] = useState('')
  const jobs = useQuery({ queryKey: ['research-jobs', token, offset], queryFn: () => listJobs(offset), refetchInterval: 4000 })
  const detail = useQuery({ queryKey: ['research-job', token, jobId], queryFn: () => getJob(jobId!),
    enabled: !!jobId, refetchInterval: (query) => ['queued', 'running'].includes(query.state.data?.status ?? '') ? 2500 : false })
  const job = detail.data
  return <main className="research-tasks">
    <header className="research-tasks-heading"><div><Link to="/chat">← {en ? 'Financial research' : '金融研究智能体'}</Link><h1>{en ? 'Research tasks' : '研究任务中心'}</h1>
      <p>{en ? 'Tasks continue while the local FinAgent service runs. Close the page and come back later.' : '本机 FinAgent 服务运行期间，任务在后台持续执行；关闭页面后仍可回来查看。'}</p></div>
      <Link className="research-primary" to="/chat">{en ? 'New research' : '新建研究'}</Link></header>
    {(jobs.error || detail.error || error) && <p role="alert">{error || (detail.error ?? jobs.error)?.message}</p>}
    <div className={`research-task-layout ${jobId ? 'with-report' : ''}`}><aside className="research-task-list">
      {jobs.isLoading && <p>{en ? 'Loading…' : '加载中…'}</p>}
      {jobs.data?.jobs.length === 0 && <p>{en ? 'No tasks yet. Submit a question in auto mode.' : '暂无任务，回到对话页以自动模式提交研究问题即可。'}</p>}
      {jobs.data?.jobs.map((item) => <Link key={item.id} to={`/research/tasks/${item.id}`} className={`research-task-card ${item.id === jobId ? 'selected' : ''}`}>
        <div><span className={`research-task-status ${item.status}`}>{jobStage(item.stage, en)}</span><small>{new Date(item.created_at).toLocaleString()}</small></div>
        <h3>{item.request.question}</h3><p>{item.request.ticker || (en ? 'Open research' : '综合研究')} · {item.source === 'personal' ? (en ? 'My API' : '我的 API') : item.source === 'codex' ? 'Codex' : (en ? 'Local default' : '本机默认模型')}</p>
      </Link>)}
      <div className="research-task-pagination"><button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 50))}>{en ? 'Previous' : '上一页'}</button>
        <button disabled={jobs.data?.next_offset == null} onClick={() => setOffset(jobs.data!.next_offset!)}>{en ? 'Next' : '下一页'}</button></div>
    </aside>
    {jobId && <section className="research-task-report">{detail.isLoading ? <p>{en ? 'Loading report…' : '正在读取研报…'}</p> : job && <>
      <header><span className={`research-task-status ${job.status}`}>{jobStage(job.stage, en)}</span><h2>{job.request.question}</h2></header>
      {['queued', 'running'].includes(job.status) && <p role="status">{en ? 'Running on your local service. You can leave this page.' : '任务在本机后台执行中，可以离开此页面。'}</p>}
      {job.error && <p role="alert">{job.error}</p>}
      {['failed', 'interrupted'].includes(job.status) && <button className="research-primary" disabled={retrying} onClick={async () => {
        setRetrying(true); setError('')
        try { const next = await submitJob(job.request, job.source, crypto.randomUUID()); await jobs.refetch(); navigate(`/research/tasks/${next.id}`) }
        catch (e) { setError(e instanceof Error ? e.message : String(e)) } finally { setRetrying(false) }
      }}>{retrying ? (en ? 'Submitting…' : '提交中…') : (en ? 'Retry with original model' : '使用原模型重新研究')}</button>}
      {job.result && <AssistantResult result={job.result} lang={en ? 'en' : 'zh'} defaultThinkingOpen={false} />}
    </>}</section>}
    </div>
  </main>
}
