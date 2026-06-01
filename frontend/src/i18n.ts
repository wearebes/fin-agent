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
  deleteProject: { zh: '删除项目', en: 'Delete project' },
  deleteSession: { zh: '删除会话', en: 'Delete session' },
  confirmDelete: { zh: '再次点击确认删除', en: 'Click again to confirm delete' },
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

  // user center
  navUser: { zh: '用户中心', en: 'User Center' },
  userCenter: { zh: '用户中心', en: 'User Center' },
  userLogin: { zh: '登录', en: 'Login' },
  userRegister: { zh: '注册', en: 'Register' },
  userProfile: { zh: '个人资料', en: 'Profile' },
  userPassword: { zh: '修改密码', en: 'Change Password' },
  loginSubtitle: { zh: '登录你的 FinAgent 账户', en: 'Sign in to your FinAgent account' },
  registerSubtitle: { zh: '创建一个新的 FinAgent 账户', en: 'Create a new FinAgent account' },
  usernameOrEmail: { zh: '用户名或邮箱', en: 'Username or email' },
  usernameOrEmailPh: { zh: '请输入用户名或邮箱', en: 'Enter username or email' },
  username: { zh: '用户名', en: 'Username' },
  usernamePh: { zh: '请输入用户名', en: 'Enter username' },
  email: { zh: '邮箱', en: 'Email' },
  emailPh: { zh: '请输入邮箱地址', en: 'Enter email address' },
  displayName: { zh: '显示名称', en: 'Display name' },
  displayNamePh: { zh: '可选，展示用的名称', en: 'Optional, display name' },
  password: { zh: '密码', en: 'Password' },
  passwordPh: { zh: '请输入密码', en: 'Enter password' },
  confirmPassword: { zh: '确认密码', en: 'Confirm password' },
  confirmPasswordPh: { zh: '再次输入密码', en: 'Enter password again' },
  passwordMismatch: { zh: '两次密码不一致', en: 'Passwords do not match' },
  loggingIn: { zh: '登录中…', en: 'Signing in…' },
  registering: { zh: '注册中…', en: 'Registering…' },
  noAccount: { zh: '没有账户？', en: "Don't have an account?" },
  hasAccount: { zh: '已有账户？', en: 'Already have an account?' },
  loginRequired: { zh: '请先登录', en: 'Please login first' },
  changePassword: { zh: '修改密码', en: 'Change Password' },
  oldPassword: { zh: '当前密码', en: 'Current password' },
  oldPasswordPh: { zh: '请输入当前密码', en: 'Enter current password' },
  newPassword: { zh: '新密码', en: 'New password' },
  newPasswordPh: { zh: '请输入新密码', en: 'Enter new password' },
  confirmNewPassword: { zh: '确认新密码', en: 'Confirm new password' },
  passwordChanged: { zh: '密码修改成功', en: 'Password changed successfully' },
  edit: { zh: '编辑', en: 'Edit' },
  save: { zh: '保存', en: 'Save' },
  saving: { zh: '保存中…', en: 'Saving…' },
  cancel: { zh: '取消', en: 'Cancel' },
  avatarUrl: { zh: '头像链接', en: 'Avatar URL' },
  avatarUrlPh: { zh: '输入头像图片链接', en: 'Enter avatar image URL' },
  registeredAt: { zh: '注册时间', en: 'Registered at' },
  logout: { zh: '退出登录', en: 'Log out' },
}

export function translate(lang: Lang, key: string): string {
  return D[key]?.[lang] ?? key
}
