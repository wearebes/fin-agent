# Fin-agent：开源调研与轻量工程改良（2026-08-31）

本轮直接改良现有 Python/FastAPI + React 项目，不重做架构、不替换金融数据接口、不引入运行依赖。验证使用模拟模型、模拟数据和本地数据库，未调用付费模型或金融数据服务，未修改密钥。

## 1. GitHub 定向调研

Stars 来自本次 GitHub REST API 查询，是 2026-08-31 的快照，不代表性能排名。阅读了下列固定版本中的实际源码；对 README 宣传与已检查代码作区分。

| 项目 / Stars | 技术栈与亮点 | 核心代码、工程实践与适配判断 |
|---|---|---|
| [Dexter](https://github.com/virattt/dexter) / 27,558 | TypeScript、Bun，金融研究工具循环 | `src/agent/agent.ts` 独立递增 iteration、限制循环、处理模型异常；`tool-executor.ts` 分离执行、权限决策和事件；适合借鉴执行预算、工具边界和证据记录。README 标注 MIT，但本次元数据没有识别出许可，本轮不复制代码。 |
| [FinRobot](https://github.com/AI4Finance-Foundation/FinRobot) / 7,890 | 本轮深入的 `finrobot/` 使用 Python/AutoGen；最新 README 另介绍 PydanticAI/FastAPI/React/Tauri Desktop | `agents/workflow.py` 组织角色和工具，`agents/prompts.py` 区分职责与终止条件；`functional/reportlab.py` 组合正文和图表。可借鉴报告分层与结构化输出，不能照搬其返回 traceback 的异常方式。Desktop 新体系未全面审计，不据此宣称已验证其全部能力。Apache-2.0。 |
| [OpenBB](https://github.com/OpenBB-finance/OpenBB) / 72,519 | Python、FastAPI，金融数据平台及分析工具生态 | `provider/abstract/fetcher.py` 将参数转换、提取、结果转换分开，并提供契约测试；`provider/utils/errors.py` 区分空数据和未授权。借鉴参数与结果校验，不引入整个平台，不改变现有数据商路由。仓库 LICENSE 为 AGPL-3.0，本轮不复制代码。 |
| [FinAgent / DVampire](https://github.com/DVampire/FinAgent) / 76 | 多模态金融交易论文配套 Python 实现，研究参考价值与 Stars 分开评估 | `prompt/custom.py` 组装文本与图像输入并校验结果键；`prompt/trading/decision.py` 有结构化结果检查、有上限的重试和 `call_provider=False` 的结果回放。借鉴结构化校验和离线验证；图像理解、向量记忆、交易决策不移植。MIT。 |
| [TradingAgents-CN](https://github.com/hsliuping/TradingAgents-CN) / 31,484 | 中文金融研究应用，FastAPI、Vue 3、MongoDB/Redis | `app/routers/auth_db.py` 展示登录态检查与业务校验分离，`app/middleware/error_handler.py` 区分错误类别。**仅作产品与权限边界对照**：`app/`、`frontend/` 为专有许可，不是可直接复制的开源资产。本轮鉴权修复依据本地代码独立实现。 |

这五个项目分别覆盖研究报告、金融数据与分析、图文输出、多模态研究、带用户管理的金融 AI 应用。没有通过安装或运行上游项目来验证其宣传的收益率、准确率或性能。

### 固定版本源码与许可来源

- Dexter：[`agent.ts`](https://github.com/virattt/dexter/blob/ecaed3011f24ea24ef687ab536aa7f22f7294038/src/agent/agent.ts)、[`tool-executor.ts`](https://github.com/virattt/dexter/blob/ecaed3011f24ea24ef687ab536aa7f22f7294038/src/agent/tool-executor.ts)、[`README`](https://github.com/virattt/dexter/blob/ecaed3011f24ea24ef687ab536aa7f22f7294038/README.md)。
- FinRobot：[`workflow.py`](https://github.com/AI4Finance-Foundation/FinRobot/blob/d221910096de87579b02f8f0674652bf1a175f51/finrobot/agents/workflow.py)、[`prompts.py`](https://github.com/AI4Finance-Foundation/FinRobot/blob/d221910096de87579b02f8f0674652bf1a175f51/finrobot/agents/prompts.py)、[`reportlab.py`](https://github.com/AI4Finance-Foundation/FinRobot/blob/d221910096de87579b02f8f0674652bf1a175f51/finrobot/functional/reportlab.py)。
- OpenBB：[`fetcher.py`](https://github.com/OpenBB-finance/OpenBB/blob/3e071fcc2cd9f891cac6040ae60296dba76dab46/openbb_platform/core/openbb_core/provider/abstract/fetcher.py)、[`errors.py`](https://github.com/OpenBB-finance/OpenBB/blob/3e071fcc2cd9f891cac6040ae60296dba76dab46/openbb_platform/core/openbb_core/provider/utils/errors.py)、[`LICENSE`](https://github.com/OpenBB-finance/OpenBB/blob/3e071fcc2cd9f891cac6040ae60296dba76dab46/LICENSE)。
- FinAgent：[`custom.py`](https://github.com/DVampire/FinAgent/blob/17248a0b8b729ee3e093e30bb7bea7f52181f363/finagent/prompt/custom.py)、[`decision.py`](https://github.com/DVampire/FinAgent/blob/17248a0b8b729ee3e093e30bb7bea7f52181f363/finagent/prompt/trading/decision.py)。
- TradingAgents-CN：[`auth_db.py`](https://github.com/hsliuping/TradingAgents-CN/blob/74783e8817d6cf6de29867880631cc555153f36b/app/routers/auth_db.py)、[`error_handler.py`](https://github.com/hsliuping/TradingAgents-CN/blob/74783e8817d6cf6de29867880631cc555153f36b/app/middleware/error_handler.py)、[`app/LICENSE`](https://github.com/hsliuping/TradingAgents-CN/blob/74783e8817d6cf6de29867880631cc555153f36b/app/LICENSE)。

## 2. 可复用资产与差距清单

“成本”指相对改造量，不是工时承诺。全部落地代码为针对现有项目的独立实现，没有粘贴上游代码或引入上游框架。

| 优先级 / 资产 | 来源思路 | 当前差距 | 成本 / 价值 | 本轮状态 |
|---|---|---|---|---|
| 立刻可改：独立迭代预算、重复调用识别 | Dexter | 未知工具不计数，可能无限循环 | 低 / 限制无效调用 | 已落实；每次模型决策计数，重复有效调用停止 |
| 立刻可改：结构化数值证据 | OpenBB 数据契约、FinRobot 报告分层 | 财报只剩条数与年份，工具结果截断到 500 字符 | 低 / 提高结论可追溯性 | 已落实；保留所选完整财报记录 |
| 立刻可改：明确失败与严格审查结果 | OpenBB 错误分类、FinAgent 结果校验 | 用 trace 中的 failed 判定状态；审查异常默认通过 | 低 / 避免伪成功 | 已落实；内部失败列表、严格布尔值、失败报告保留供排查 |
| 立刻可改：离线模拟、阻止意外外网 | FinAgent 离线回放思路，现有 pytest | 测试可能读取真实 `.env`，部分数据调用未模拟 | 低 / 验证不消耗接口额度 | 已落实；默认隔离配置并拦截测试外网 |
| 小幅改造：工具输入 JSON Schema | Dexter 工具边界、OpenBB 参数契约 | 模型只知道工具名，不知道必填字段和范围 | 低 / 降低无效参数调用 | 已落实；使用已有 Pydantic，保留文本 tool_call 协议 |
| 小幅改造：同步 I/O 卸载 | OpenBB 同步/异步提取边界 | 同步检索与行情调用占住异步事件循环 | 低 / 使其他请求可继续处理 | 已落实；标准库 `asyncio.to_thread`，不并行轰击数据商 |
| 小幅改造：一致的账号鉴权错误码 | TradingAgents-CN 产品对照，本地独立修复 | 无效 token 在修改资料/密码时被当作 404/400 | 低 / 客户端能识别登录失效 | 已落实；先鉴权，再做业务校验；账号接口统一 401 |
| 小幅改造：图表与报告导出组件 | FinRobot ReportLab、FinAgent 图像输入 | Markdown 可展示图文，但没有完整图表生成、PDF 导出链路 | 中 / 提高交付质量 | 本轮不新增；保留现有 Markdown 图文能力 |
| 后续架构升级：资源归属、后台任务、流式进度 | 金融应用的用户隔离与任务管理模式 | 研究接口开放、会话仅浏览器存储、请求等待全流程 | 高 / 多用户与部署能力 | 留待后续；避免破坏现有匿名客户端 |
| 后续架构升级：多模态、量化回测、长期记忆 | FinAgent、OpenBB、FinRobot | 量化页面仍是占位；无完整回测引擎与长期记忆 | 高 / 新能力 | 留待后续；不把页面入口算作已实现功能 |

## 3. 已落地核心代码及说明

### 有界工具循环

对应 `src/fin_agent/workflows/research/stages/pipeline.py`，参考 Dexter 独立迭代计数的思路。保留 `max_tool_calls`，同时启用原有但未执行的 `max_iterations`；未知工具、参数错误都无法绕过后者。无需增加模型调用、重试服务或依赖。

```python
while (
    len(ctx.tool_calls) < deps.config.max_tool_calls
    and ctx.iteration < deps.config.max_iterations
):
    ctx.iteration += 1
    # 参数经过 Pydantic 校验，已执行过的同名同参数调用直接停止。
```

### 财报证据与 Prompt

`stages/core.py`、`stages/tools.py` 将财报按财年/季度排序，保留最新最多 8 条记录中的非空字段，包括营收、净利润、资产、现金流等实际返回值。没有替换 AKShare、FMP、YFinance 的请求、端点、合并或回退逻辑。

`evidence.py` 对结构化列表按完整记录控制大小，超过预算时记录 `omitted_records`，不在数值或 JSON 中间切断。工具列表证据默认上限 12,000 字符，写作与审查共享 60,000 字符的证据视图；这是字符预算，并非精确 token 计量。财报的 8 条窗口与配置中的 evidence_limit 仍会限制可见历史，不能称为原始数据全量存档。

```python
rows = [r.model_dump(mode="json", exclude_none=True) for r in records[:8]]
return compact_records(rows)
```

Prompt 明确要求保留时间和数字口径、标注缺失币种/单位、区分事实和判断、不得编造来源或图表，并将外部内容视为数据而非指令。审查模型收到与写作模型相同的证据，而不再只读报告。这些约束降低风险，但不能保证抵御全部提示注入或保证报告准确。

### 失败状态和审查

对应 `context.py`、`graph.py`、`services/research.py`、`stages/pipeline.py`。参考结构化校验与错误分类思路，仍使用现有 completed/failed 状态及 API 字段。

```python
class ReviewDecision(BaseModel):
    passed: StrictBool
    feedback: str = ""

# ResearchService.run()
if ctx.failed_stages or not ctx.report.strip():
    status = RunStatus.FAILED
```

模型返回空报告、审查 JSON 无效、`passed` 是字符串、审查拒绝，都会明确失败；问题里自然出现 failed 一词不再影响状态。空公司资料或空分析师结果不再算作证据。没有证据时跳过报告模型调用，生成报告失败时跳过审查。本轮不自动重试审查或重写报告，防止隐性增加调用成本。前端会提示失败内容需要核验；报告及 trace 仍可保存和查看。

### 工具契约、性能与账号接口

- `tool_inputs.py` 为 6 个现有工具提供输入模型；注册表输出 JSON Schema，工具执行前验证必填字段、枚举和范围。仍兼容原 `register(name, fn)` 及模型的 fenced `tool_call` 文本，不强制支持供应商原生 function calling。
- 检索和工具包装器使用 `asyncio.to_thread` 调用原同步 adapter，维持单次研究内的取数顺序。它不等于队列、取消任务或数据商超时控制；长时间阻塞的底层 SDK 仍受原有超时机制约束。
- 账号资料与改密先完成身份检查，再做业务验证；未修改注册/登录请求体、成功响应、JWT 算法或用户存储。未给研究接口突然加登录门槛，因此**研究结果的用户归属和隔离仍未完成**。
- 前端保留聊天工作台、会话、用户页面、Markdown 图片/表格渲染和量化入口；移除会话删除中的未使用变量。未更改用户已有的 CSS 修改。

## 4. 验证与兼容边界

- 第一轮离线基线：131 通过、3 失败。一个旧 API 测试未完整模拟行情请求而被网络拦截；另两个是手写 `.env.example` 与自动生成文本的错误逐字比较，以及过时的默认工具次数断言。本轮修正了模拟与测试契约，没有把产品默认值改回旧值。
- 当前离线测试：161 通过。覆盖财报数值进入写作/审查、未知工具和无效参数循环上限、重复调用、500 字符以后的证据、空元数据过滤、审查失败、空模型响应、HTTP/CLI 结果、SQLite 存储、登录/资料/改密、无效身份 401，以及等待搜索时事件循环仍可处理其他任务。
- 修改范围的 Ruff 检查通过；研究流程与研究服务的 mypy 检查通过。
- 前端 TypeScript 检查、Vite 生产构建通过；构建产物放在临时验收目录，未覆盖现有 `frontend/dist`，未启动或发布服务。
- React 离线 HTML 渲染检查通过：中英文失败提示、正常完成状态、Markdown 图片与表格、证据展示、量化页面入口。没有进行浏览器视觉验收或真实研报图表生成。
- 本地已装 `lucide-react@0.453.0` 缺少类型文件：从公开 npm 同版本包校验 SHA-512 后仅恢复缺失 `.d.ts`。未修改 package.json、锁文件或新增依赖。
- API 请求/响应字段、数据库表结构、金融 provider 文件均未改变。旧记录继续读取；原本误报完成的失败运行会正确返回 `status=failed`，属于明确的行为修正。
- 没有真实模型/金融数据联调，没有准确率、收益率或端到端性能提升数字。模型审查仍是辅助检查；本轮通过的离线测试不等于研报内容获得事实认证。
- 保留原有未提交修改；未提交 Git commit、推送或部署。量化引擎、数据看板业务、完整图文导出、研究权限隔离不能视为本轮已补齐。

在项目根目录运行 `python -m pytest -q` 即使用默认离线隔离；测试遇到未模拟的外网访问会失败，不会改用真实密钥补跑。
