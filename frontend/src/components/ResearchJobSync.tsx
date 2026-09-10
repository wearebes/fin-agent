import { useEffect } from 'react'
import { getJob, getJobByClient } from '../api/jobs'
import { ApiRequestError } from '../api/auth'
import { useWorkspace } from '../store/workspace'
import { useUserStore } from '../store/user'

/** Polling is just observation: unmounts and network loss do not cancel server tasks. */
export default function ResearchJobSync() {
  const token = useUserStore((s) => s.token)
  useEffect(() => {
    let active = true
    let timer: ReturnType<typeof setTimeout>
    async function refresh() {
      const pending = useWorkspace.getState().messages.filter((m) => m.jobClientId && m.status === 'running')
      for (const message of pending) {
        try {
          const job = message.jobId ? await getJob(message.jobId)
            : await getJobByClient(message.jobClientId!)
          if (!active || !job) continue
          const terminal = !['queued', 'running'].includes(job.status)
          useWorkspace.getState().updateMessage(message.id, {
            jobId: job.id,
            progress: { stage: job.stage, status: terminal ? 'completed' : 'running' },
            status: terminal ? job.status === 'completed' ? 'completed' : 'failed' : 'running',
            error: job.error ?? undefined,
            ...(terminal ? { result: job.result ?? undefined,
              durationMs: Date.parse(job.updated_at) - Date.parse(job.created_at) } : {}),
          })
        } catch (error) {
          // Only a confirmed missing submission can become retryable; network loss is not failure.
          if (active && !message.jobId && Date.now() - message.createdAt > 10000
            && error instanceof ApiRequestError && error.status === 404) {
            useWorkspace.getState().updateMessage(message.id, {
              status: 'failed', error: '后台未收到该任务，请重新提交。 / Task was not received; please retry.',
            })
          }
        }
      }
      if (active) timer = setTimeout(refresh, 2500)
    }
    void refresh()
    return () => { active = false; clearTimeout(timer) }
  }, [token])
  return null
}
