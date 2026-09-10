import { request } from './auth'
import type { ResearchJob, ResearchRequest } from '../types'

export const listJobs = (offset = 0) => request<{ jobs: ResearchJob[]; next_offset: number | null }>(
  `/v1/research/jobs?offset=${offset}`, { cache: 'no-store' },
)
export const getJob = (id: string) => request<ResearchJob>(
  `/v1/research/jobs/${encodeURIComponent(id)}`, { cache: 'no-store' },
)
export const getJobByClient = (id: string) => request<ResearchJob>(
  `/v1/research/jobs/by-client/${encodeURIComponent(id)}`, { cache: 'no-store' },
)
export const submitJob = (input: ResearchRequest, source: ResearchJob['source'], clientId: string) =>
  request<ResearchJob>('/v1/research/jobs', {
    method: 'POST', body: JSON.stringify({ request: input, source, client_id: clientId }),
  })

export const jobStage = (stage: string, en = false) => {
  const labels: Record<string, [string, string]> = {
    queued: ['等待执行', 'Queued'], intake: ['准备研究', 'Preparing'], plan: ['制定检索计划', 'Planning'],
    retrieve: ['获取数据', 'Retrieving data'], 'tool-exec': ['分析证据', 'Analyzing evidence'],
    synthesize: ['撰写研报', 'Writing report'], review: ['核对结论', 'Reviewing'],
    persist: ['保存研报', 'Saving'], completed: ['已完成', 'Completed'], failed: ['未完成', 'Failed'],
    interrupted: ['已中断', 'Interrupted'],
  }
  return labels[stage]?.[en ? 1 : 0] ?? (en ? 'Analyzing' : '分析中')
}
