import type { Message } from '../store/workspace'
import type { Lang, ResearchTurn, RunResult } from '../types'

export function recentResearch(messages: Message[], sessionId: string | null): ResearchTurn[] {
  return messages
    .filter((message) => message.sessionId === sessionId && message.role === 'assistant'
      && message.result?.status === 'completed')
    .slice(-3)
    .map(({ result }) => ({
      question: result!.request.question.slice(0, 1000),
      answer: result!.report.slice(0, 4000),
      ticker: result!.request.ticker?.slice(0, 64) || null,
    }))
}

export function safeSourceUrl(value: unknown): string | null {
  if (typeof value !== 'string') return null
  try {
    const url = new URL(value)
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null
  } catch {
    return null
  }
}

export function reportMarkdown(result: RunResult, lang: Lang): string {
  const warning = result.status !== 'completed'
    ? (lang === 'zh' ? '> 本次研究未完成或未通过审查，请勿直接采用。\n\n'
      : '> This research is incomplete or unverified; check before use.\n\n')
    : ''
  const sources = result.evidence.map((item, index) =>
    `### ${index + 1}. ${item.source}\n\n${item.summary}`,
  ).join('\n\n')
  return `${warning}# ${result.request.question}\n\n${result.report}\n\n## ${lang === 'zh' ? '数据与来源' : 'Data & sources'}\n\n${sources}\n`
}
