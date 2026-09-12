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

export function researchIssue(result: RunResult, lang: Lang): string | null {
  if (result.status !== 'failed') return null
  const details = (result.trace ?? []).map((item) => item.detail)
  if (details.some((detail) => detail.startsWith('Report generation failed:'))
    && !details.some((detail) => detail.includes('no evidence available'))) return result.report
      || (lang === 'zh' ? '正文生成失败，请查看执行记录。' : 'Draft generation failed; check the execution log.')
  if (details.some((detail) => detail.includes('no evidence available'))) return lang === 'zh'
    ? '未取得可用资料：请检查数据源或明确公司名称与代码。模型连接成功不代表行情、财务和搜索数据源都可用。'
    : 'No usable evidence was retrieved. Check data sources or specify the company and ticker.'
  if (details.some((detail) => detail.includes('Review could not be completed'))) return lang === 'zh'
    ? '正文已生成，自动复核未完成：复核模型未返回有效的审核结果。报告和图表已保留，使用前请核验数据与来源。'
    : 'Draft generated; automated review returned no valid decision. Report and charts are retained for verification.'
  if (details.some((detail) => detail.includes('Review did not pass'))) return lang === 'zh'
    ? '正文已生成，但未通过自动复核。请查看执行记录中的复核意见，核对后再使用。'
    : 'Draft generated but rejected by automated review. Check the review feedback before use.'
  return null
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
