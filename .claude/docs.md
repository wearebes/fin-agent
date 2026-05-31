# fin-agent 需求与架构基线

## 1. 文档目的

这份文档用于在继续开发前，先统一以下问题：

- `fin-agent` 现在真实已经有什么
- 当前最关键缺口是什么
- 下一阶段先做什么，不做什么
- 哪些框架和结构继续沿用，哪些暂时不要引入

当前事实以源码、配置文件、命令入口和最小运行验证为准，不以 README 或 `.claude/AGENT.md` 的单独表述为准。

---

## 2. 当前真实状态

### 2.1 已经存在的部分

从当前源码看，这个仓库已经不是“只有空骨架”：

- 配置系统已经存在：
  - `src/fin_agent/bootstrap/settings.py`
  - 采用 `pydantic-settings + layered YAML + .env + 环境变量`
- 组合根和依赖装配已经存在：
  - `src/fin_agent/bootstrap/container.py`
- CLI 和 API 入口已经存在：
  - `src/fin_agent/bootstrap/cli.py`
  - `src/fin_agent/bootstrap/app.py`
  - `src/fin_agent/interfaces/api/router.py`
- research workflow 已经存在，并且按 stage 执行：
  - `src/fin_agent/workflows/research/graph.py`
  - stages: `intake -> plan -> retrieve -> tool-exec -> synthesize -> review -> persist`
- provider adapter 已经存在：
  - OpenAI: `src/fin_agent/adapters/llm/openai/`
  - Exa: `src/fin_agent/adapters/search/exa/`
  - YFinance: `src/fin_agent/adapters/market_data/yfinance/`
  - AkShare: `src/fin_agent/adapters/market_data/akshare/`
- 市场数据路由已经存在：
  - `src/fin_agent/adapters/market_data/router.py`
- 运行结果存储接口已经存在，但当前实现只有内存版：
  - `src/fin_agent/storage/run_store.py`

### 2.2 已经验证到的运行事实

- 本机存在 conda 环境：`fin-agent`
- 该环境可以完成最小 import 和 settings 加载
- 当前环境里已安装关键运行依赖：
  - `fastapi`
  - `pydantic-settings`
  - `PyYAML`
  - `openai`
  - `exa-py`
  - `yfinance`
  - `akshare`

### 2.3 当前没有闭环的部分

- `RunResult` 还不是一个完整的“研究交付物”契约：
  - `src/fin_agent/domain/types.py` 里的 `RunResult` 只有 `evidence` 和 `trace`
  - 但 workflow context 里已经有 `report`、`review_passed`、`review_feedback`、`tool_calls`
  - 这些内容最后没有进入 API/CLI 输出
- `persist` stage 目前基本还是空实现：
  - `src/fin_agent/workflows/research/stages/pipeline.py`
- 存储目前只有 `InMemoryRunStore`，进程退出后结果丢失
- 当前 workflow 中混用了 async surface 和 sync provider 调用：
  - API/service/workflow 是 async
  - Exa、YFinance、AkShare 路径大多还是同步调用
- README 与实际源码状态不一致
- `.claude/AGENT.md` 与 README 也不一致
- README 引用了 `docs/developer-guide.md`，但当前仓库里没有这个文件
- `Makefile` 里有 `test: pytest`，但当前 `fin-agent` conda 环境里没有 `pytest`

---

## 3. 当前最关键的问题

### 3.1 文档口径漂移

目前至少有三套口径：

- README：说真实 provider 还没接通
- `.claude/AGENT.md`：说真实 provider 已经接通，workflow 顺序执行
- 源码：确实已经有 provider client、workflow stage、tool loop，但结果契约和持久化没有闭环

如果先不统一这件事，后续开发会一直在错误前提上推进。

### 3.2 产品输出契约不清

目前不清楚一次 research run 的“完成态”到底是什么：

- 是只返回阶段计划？
- 还是要返回完整 research report？
- 是否必须带引用来源？
- 是否必须带 review 结果？
- 是否要保留 tool 调用记录和 trace？

这件事不先定义，workflow、API、存储、测试都会反复返工。

### 3.3 工程闭环不完整

当前代码已经有不少实现，但工程闭环还没补齐：

- 开发环境没有形成一条稳定的初始化路径
- 存储没有落地
- API/CLI 输出契约不完整
- 文档和测试与实现存在漂移

---

## 4. 我们现在缺什么

### 4.1 需求层缺口

我们缺一份明确的 MVP 定义，至少要回答：

- 目标用户是谁
  - 是面向内部研究员
  - 还是面向自动化研究流水线
- 支持的问题类型是什么
  - 单股票研究
  - 行业/主题研究
  - A 股 / 美股 / ETF / Crypto
- 一次 run 的标准输出是什么
  - 结构化报告
  - 引用来源
  - 关键数据摘要
  - trace / tool 调用记录
- 失败语义是什么
  - provider 失败时是否允许降级
  - 哪些失败算“部分成功”
  - 哪些失败必须返回 failed

### 4.2 工程层缺口

- 单一事实源文档缺失
  - 当前需要以 `.claude/docs.md` 作为先行基线
- 环境文档和安装流程未闭环
  - `environment.yml` 过薄
  - 当前 conda 环境缺少 `pytest`
- 持久化缺失
  - 已有 `SQLAlchemy`、`Alembic` 依赖，但没有真正落地
- 输出模型缺失
  - `RunResult` 没有承接 `report/review/tool_calls`
- 阻塞 I/O 边界不清
  - async workflow 直接调用 sync adapter，后续在 API 场景下会阻塞事件循环
- 测试和实现开始出现漂移
  - 例如 `tests/test_settings.py` 与 `ResearchWorkflowConfig` 默认值不一致

---

## 5. 建议继续沿用的框架和结构

这里不建议推倒重来。当前主骨架是合理的，应该沿用。

### 5.1 配置层

继续沿用：

- `pydantic-settings`
- layered YAML
- `.env`
- 环境变量覆盖

约束：

- 只有 `src/fin_agent/bootstrap/settings.py` 可以直接读取 YAML、`.env`、环境变量
- 其他模块只能接收 typed config，不直接读环境

### 5.2 组合根 / 依赖装配

继续沿用：

- `src/fin_agent/bootstrap/container.py`

约束：

- provider client、service、store、workflow deps 都从 container 装配
- 业务层不要反向 import `AppSettings`

### 5.3 CLI 和 API

继续沿用：

- CLI: `Typer`
- API: `FastAPI`

原因：

- 这两层已经有现成入口
- 结构简单，足够覆盖当前 MVP
- 现在还不需要为了“agent 框架化”再引入更重的外部调度层

### 5.4 工作流编排

继续沿用：

- 自定义 stage graph
  - `src/fin_agent/workflows/research/graph.py`
  - `src/fin_agent/workflows/research/stages/`

当前不建议引入：

- LangChain
- LangGraph
- Celery
- Airflow

原因：

- 当前真正缺的不是“大框架”，而是输出契约、持久化、失败语义和文档统一
- 在需求边界还不清的时候引入重框架，只会扩大复杂度

### 5.5 领域模型

继续沿用：

- `Pydantic` 作为 domain / API contract 定义方式
- 统一放在 `src/fin_agent/domain/types.py` 和相邻模块

但需要补一层明确区分：

- 请求模型
- workflow 内部上下文模型
- 对外返回模型
- 持久化实体模型

当前这几层还没有完全分清。

### 5.6 持久化

建议继续沿用已引入但未完成的技术选型：

- `SQLAlchemy`
- `Alembic`

建议结构：

- `storage/` 下保留 repository / store 抽象
- 本地开发先用 SQLite
- 后续如果需要，再切到 PostgreSQL

### 5.7 日志与可观测性

短期继续沿用：

- Python 标准库 `logging`
- `settings.logging.json` 控制 JSON 日志

但要补齐：

- `run_id`
- `stage`
- provider 名称
- error type
- latency

否则真实排障会很困难。

### 5.8 I/O 模型

建议的原则是：

- API / service / workflow 继续保持 async
- 对于同步 provider SDK，在 adapter 边界解决阻塞问题

不要把阻塞处理散落到 stages 里。后续如果需要，可以在 adapter 内部统一用线程池包装同步调用。

---

## 6. MVP 应该先做成什么样

### 6.1 我们要的不是“全能研究员”，而是“能稳定跑通的 research MVP”

第一阶段 MVP 只需要做到：

- 能接收一个 research question
- 可选接收 ticker
- 能完成规划、检索、必要的工具补充
- 能产出一个结构化 report
- 能返回 evidence / trace
- 能把结果持久化保存
- API 和 CLI 返回同一份核心结果结构

### 6.2 建议的最终输出契约

建议未来 `RunResult` 至少包含：

- `run_id`
- `status`
- `environment`
- `request`
- `providers`
- `planned_stages`
- `evidence`
- `report`
- `review`
  - `passed`
  - `feedback`
- `tool_calls`
- `trace`
- `created_at`
- `updated_at`

这样 API、CLI、存储、测试才能围绕同一个对象收敛。

---

## 7. 分阶段实施建议

### Phase 0: 基线对齐

先做这些，不做功能扩张：

- 统一文档口径
  - README
  - `.claude/docs.md`
  - `.claude/AGENT.md`
- 删除或补上失效引用
  - 例如 `docs/developer-guide.md`
- 明确当前 repo 的 source of truth
- 明确 MVP 输出契约

### Phase 1: 开发环境闭环

- 补齐 `environment.yml` 或提供明确的一步安装方式
- 让这些命令在目标环境里真实可跑：
  - `fin-agent doctor`
  - `fin-agent research run`
  - `pytest`
- 校准 `Makefile` 与真实环境要求

### Phase 2: research run 输出闭环

- 把 `report/review/tool_calls` 正式并入结果模型
- 明确成功、部分成功、失败的状态语义
- 让 API 和 CLI 使用同一份结果 contract

### Phase 3: 持久化闭环

- 从 `InMemoryRunStore` 过渡到数据库实现
- 定义 repository 接口
- 增加最少必要的数据表和迁移
- 先保证“run 可回查”，再考虑更复杂的检索能力

### Phase 4: 质量与可观测性

- 修复测试与实现漂移
- 增加集成测试分层
- 补齐日志字段
- 对 provider 错误做更清晰的分类和降级策略

---

## 8. 当前不建议优先做的事情

在下面这些问题没定之前，不建议优先投入：

- 引入更重的 agent orchestration 框架
- 做前端界面
- 做多工作流、多租户、多任务调度
- 做向量数据库、记忆系统、复杂长期状态
- 做“全市场全资产全场景”一次性铺开

当前更重要的是把单次 research run 的需求、契约和工程闭环先打通。

---

## 9. 结论

`fin-agent` 当前最缺的不是“再加一个框架”，而是：

1. 一个统一的需求和事实基线
2. 一个明确的 research run 输出契约
3. 一个可重复的开发/测试环境
4. 一个最小但完整的持久化闭环

所以后续开发原则应该是：

- 保留现有主骨架
- 先修正事实口径
- 先收敛 MVP 契约
- 再做功能扩展
