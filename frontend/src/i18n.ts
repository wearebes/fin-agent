import type { Lang } from './types'

type Entry = { zh: string; en: string }
type Dict = Record<string, Entry>

// Migrated from the legacy static/index.html `D` dictionary, extended with the
// workspace strings introduced in Phase 1.
export const D: Dict = {
  // top bar / tabs
  navAgent: { zh: '智能体对话', en: 'Agent Chat' },
  navQuant: { zh: '量化金融', en: 'Quant Finance' },

  // sidebar
  sbProjects: { zh: '项目', en: 'Projects' },
  newProject: { zh: '新建项目', en: 'New project' },
  newSession: { zh: '新建会话', en: 'New session' },
  defaultProjectName: { zh: '我的工作区', en: 'My workspace' },
  defaultSessionTitle: { zh: '新研究', en: 'New research' },

  // chat
  emptyTitle: { zh: '开始一次金融研究', en: 'Start a financial research' },
  emptyDesc: {
    zh: '输入研究问题，AI 自动完成数据采集、新闻检索与深度分析，生成结构化研究报告。',
    en: 'Ask a question — the agent gathers data, searches news, performs deep analysis, and returns a structured report.',
  },
  phQ: {
    zh: '例如：比亚迪近三年盈利趋势如何？是否有持续增长动力？',
    en: "e.g. What is BYD's profit trend over the past 3 years?",
  },
  phT: { zh: '股票代码（可选），如 AAPL、002594.SZ', en: 'Ticker (optional), e.g. AAPL, 002594.SZ' },
  send: { zh: '开始研究', en: 'Start research' },
  sending: { zh: '研究进行中…', en: 'Researching…' },
  clear: { zh: '清空会话', en: 'Clear chat' },
  clearConfirm: { zh: '确定清空当前会话的所有消息？', en: 'Clear all messages in this session?' },
  retry: { zh: '重试', en: 'Retry' },
  you: { zh: '你', en: 'You' },
  assistant: { zh: '智能体', en: 'Agent' },
  composerHint: { zh: 'Ctrl/⌘ + Enter 发送', en: 'Ctrl/⌘ + Enter to send' },

  // result blocks
  running: { zh: '研究进行中', en: 'Research in progress' },
  completed: { zh: '研究完成', en: 'Research completed' },
  failed: { zh: '研究失败', en: 'Research failed' },
  pending: { zh: '排队中', en: 'Pending' },
  runId: { zh: '运行 ID', en: 'Run ID' },
  env: { zh: '环境', en: 'Env' },
  stages: { zh: '计划阶段', en: 'Planned stages' },
  report: { zh: '研究报告', en: 'Research report' },
  evidence: { zh: '证据来源', en: 'Evidence' },
  trace: { zh: '执行追踪', en: 'Execution trace' },
  source: { zh: '来源', en: 'Source' },
  errorTitle: { zh: '请求出错', en: 'Request failed' },

  // quant
  quantTitle: { zh: '量化金融', en: 'Quant Finance' },
  quantDesc: {
    zh: '策略回测、模型调试、模拟交易与实盘对接，一站式量化研发平台。',
    en: 'Strategy backtesting, model debugging, paper trading, and live execution.',
  },
  qBacktest: { zh: '策略回测', en: 'Strategy Backtest' },
  qBacktestD: {
    zh: '基于历史数据验证策略表现，支持多因子模型与自定义指标',
    en: 'Validate strategy performance on historical data with multi-factor models',
  },
  qModel: { zh: '模型调试', en: 'Model Debug' },
  qModelD: {
    zh: '参数调优、过拟合检测与模型诊断，快速迭代策略逻辑',
    en: 'Parameter tuning, overfit detection, and model diagnostics',
  },
  qPaper: { zh: '模拟交易', en: 'Paper Trading' },
  qPaperD: {
    zh: '零资金风险的策略模拟运行，实时跟踪虚拟持仓表现',
    en: 'Risk-free strategy simulation with real-time virtual portfolio tracking',
  },
  qLive: { zh: '实盘对接', en: 'Live Execution' },
  qLiveD: {
    zh: '信号生成与交易执行对接，支持主流券商 API',
    en: 'Signal generation and execution via major broker APIs',
  },
  soon: { zh: '即将上线', en: 'Coming Soon' },

  // research process panel
  researchProcess: { zh: '研究过程', en: 'Research process' },
  processOn: { zh: '已开启默认展开', en: 'Default expanded' },
  processOff: { zh: '已关闭默认展开', en: 'Default collapsed' },
  duration: { zh: '耗时', en: 'Duration' },

  // footer
  footer: { zh: '由 AI 驱动的金融研究平台', en: 'AI-Powered Financial Research Platform' },
}

export function translate(lang: Lang, key: string): string {
  return D[key]?.[lang] ?? key
}
