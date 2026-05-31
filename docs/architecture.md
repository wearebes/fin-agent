# fin-agent 项目架构分析

> 版本：branch `front` · 生成时间：2026-05-30

---

## 1. 项目定位

fin-agent 是一个**面向金融研究的 AI Agent 系统**。用户通过 Web 前端提交研究问题，后台自动编排多阶段 LLM 工作流（检索计划 → 信息收集 → 工具调用 → 综合报告 → 质检），最终输出结构化的金融研究报告。

---

## 2. 整体架构分层

```
┌─────────────────────────────────────────────────────────┐
│                     前端界面 (静态 HTML)                   │
│           static/index.html  ·  Apple 风格 UI             │
│           多语言支持 (zh / en)  ·  实时 trace 展示          │
└────────────────────────┬────────────────────────────────┘
                         │ POST /v1/research/runs
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    API 接口层                              │
│      interfaces/api/router.py                            │
│      ResearchRequest → ResearchService.run()             │
│      GET /v1/research/runs/{id}/trace  (trace 查询)       │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    服务层                                  │
│      services/research.py                                │
│      · 创建 ResearchContext                               │
│      · 调用 execute_workflow()                            │
│      · 组装 RunResult → RunStore.save()                   │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                  工作流引擎（7 阶段固定图）                   │
│      workflows/research/graph.py                         │
│                                                          │
│   intake → plan → retrieve → tool-exec →                 │
│   synthesize → review → persist                          │
└────────────────────────┬────────────────────────────────┘
                         │ 依赖注入
                         ▼
┌─────────────────────────────────────────────────────────┐
│                   适配器层 (可插拔)                          │
│                                                          │
│  LLM           │ Search          │ Market Data           │
│  ─────────     │ ──────────      │ ──────────────        │
│  OpenAI        │ Exa / Tavily    │ yfinance / AKShare /  │
│  (gpt-4.1-mini)│                 │ FMP                   │
└────────────────┴─────────────────┴───────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    存储层                                  │
│      storage/run_store.py  (InMemory / SQLAlchemy)        │
│      storage/db_store.py   (SQLite by default)            │
└─────────────────────────────────────────────────────────┘
```

---

## 3. 工作流阶段详解

### 阶段流水线（graph.py）

```
intake
  └─ 解析请求，生成 run_id，初始化 ResearchContext

plan (core.py:20)
  └─ LLM 生成检索计划 → JSON → 决定后续 retrieve 的查询策略

retrieve (core.py)
  └─ 调用 Search 适配器 + company_info 预取
  └─ 每条结果封装为 EvidenceItem(source="...")

tool-exec (pipeline.py:16)
  └─ LLM 循环决策：输出 tool_call{...} 或 done
  └─ 最多调用 max_tool_calls 次（默认 3）
  └─ 可调用 6 种工具（见工具表）

synthesize (pipeline.py:31)
  └─ 汇总全部 evidence → LLM 生成结构化报告
  └─ 报告结构：Executive Summary / Key Findings /
               Risk Factors / Conclusion & Outlook

review (pipeline.py:42)
  └─ LLM 审核报告质量 → JSON {passed, feedback}
  └─ ⚠️ 结果当前未暴露给前端

persist
  └─ 仅追加 trace 日志（真正持久化在 research.py:69）
```

---

## 4. 工具调用体系（tool-exec 阶段）

| 工具名 | 数据来源 | 主要参数 | 返回内容 |
|---|---|---|---|
| `search` | Exa / Tavily | query | 网页标题/URL/摘要 |
| `market_data` | yfinance / AKShare / FMP | ticker, asset_type, period | 最近 60 条行情 OHLCV |
| `financials` | yfinance / AKShare / FMP | ticker, statement_type | 最近 8 期财务数据 |
| `company_info` | yfinance / AKShare / FMP | ticker | 公司基本信息 |
| `analyst` | yfinance / FMP | ticker | 分析师评级 + 盈利预测 |
| `crypto` | yfinance | ticker, period | 最近 60 条加密货币数据 |

工具调用结果全部以 `EvidenceItem(source="tool:<工具名>")` 追加到 context，并最终注入 synthesize 阶段的 prompt。

---

## 5. 适配器与配置矩阵

### LLM 适配器

| 配置项 | 默认值 | 说明 |
|---|---|---|
| provider | openai | 目前唯一实现 |
| model | gpt-4.1-mini | 可通过 `FIN_AGENT__OPENAI__MODEL` 覆盖 |
| base_url | (OpenAI 官方) | 可配置中转代理 |
| temperature | - | 由 config 控制 |

### Market Data 路由策略（router.py）

```
请求进来
  ├─ provider = akshare → AKShare 客户端
  │     └─ 失败则 fallback 到 datacenter-web.eastmoney.com
  ├─ provider = fmp    → FMP 客户端（需 API Key）
  └─ provider = yfinance → yfinance 客户端（默认）
```

### Search 适配器

| Provider | 特点 | 需要 API Key |
|---|---|---|
| Exa | 语义搜索，结果质量高 | 是 |
| Tavily | 通用搜索，速度快 | 是 |

---

## 6. 配置加载优先级

```
代码 init 参数
  > 环境变量 (FIN_AGENT__XXX__YYY)
    > .env 文件
      > configs/environments/{env}.yaml
        > configs/base.yaml
          > Pydantic 字段默认值
```

支持三套环境：`local`（默认）、`staging`、`production`，通过 `FIN_AGENT__APP__ENVIRONMENT` 切换。

---

## 7. 数据模型速查

### 请求 → 响应流

```
ResearchRequest
  question: str       ← 必填
  ticker:   str?      ← 可选，股票代码
  template: str       ← 默认 "open_research"（⚠️ 当前无实际路由效果）
  lang:     str       ← "zh" | "en"，影响 prompt 的语言指令
        │
        ▼
RunResult
  run_id:          str
  status:          completed | failed
  environment:     local | staging | production
  request:         ResearchRequest (原样回传)
  providers:       {llm: "openai", search: "exa", market_data: "yfinance"}
  planned_stages:  ["intake", "plan", "retrieve", ...]
  report:          str    ← synthesize 阶段 LLM 输出全文
  evidence:        EvidenceItem[]  ← 最多 12 条
  trace:           TraceRecord[]   ← 各阶段执行日志
```

### Domain 数据类型（types.py 定义的结构化数据）

系统定义了完整的金融数据模型，覆盖：
- `MarketDataPoint` — OHLCV + PE/PB + 主力资金流入
- `FinancialStatementRecord` — 三表核心指标（营收/净利润/现金流）
- `AnalystRecommendation` + `EarningsEstimate` — 分析师数据
- `CompanyInfo` — 公司基本面信息
- `RiskMetrics` — Beta / VaR / Sharpe / 审计意见
- `SentimentData` — 情绪指数 / 恐慌贪婪指数 / 散户参与率
- `MacroDataPoint` — M2 / LPR / CPI / PPI / PMI / 联邦基金利率
- `CommoditySupplyChainData` — 原油 / BDI / 锂价 / 芯片交期
- `GeoPoliticalRiskData` — 关税 / 地缘风险指数 / 反垄断记录
- `QuantitativeIndicators` — RSI / MACD / 隐含波动率 / 动量因子

> 注：上述后半部分数据类型已定义结构，**适配器层尚未完整实现数据拉取**。

---

## 8. 已知设计缺口（待改进项）

| 编号 | 问题描述 | 影响 | 建议方向 |
|---|---|---|---|
| G-1 | `template` 字段无路由逻辑 | 切换模板不会切换 prompt | 新增 PromptRegistry，按 template 名索引 prompt 集合 |
| G-2 | Prompt 常量散落在 core.py / pipeline.py | 多模板难以维护 | 抽离为独立模板文件或 prompt 注册表 |
| G-3 | `review` 结果（passed/feedback）未进入 RunResult | 前端看不到质检结论 | RunResult 新增 `review_passed`、`review_feedback` 字段 |
| G-4 | `tool_calls` 明细未进入 RunResult | 前端看不到工具真实调用链路 | RunResult 新增 `tool_calls` 列表 |
| G-5 | `persist` stage 只写 trace，真正持久化在 research.py | 阶段语义与副作用分离 | 将 RunStore.save() 移入 persist stage |
| G-6 | evidence source 用 inline 字符串（如 `company_info:MSFT`）而非结构化引用系统 | 无法做精确来源追溯 | 定义 CitationRef 类型 |

---

## 9. 目录结构速查

```
fin-agent/
├── configs/
│   ├── base.yaml                   # 基础配置
│   └── environments/
│       ├── local.yaml
│       ├── staging.yaml
│       └── production.yaml
├── src/fin_agent/
│   ├── bootstrap/
│   │   ├── settings.py             # 分层配置加载
│   │   ├── container.py            # 依赖装配（DI 容器）
│   │   ├── app.py                  # FastAPI app 工厂
│   │   └── cli.py                  # CLI 入口
│   ├── domain/
│   │   ├── types.py                # 全部 Pydantic 数据模型
│   │   └── constants.py            # Enum 常量定义
│   ├── interfaces/api/
│   │   └── router.py               # FastAPI 路由
│   ├── services/
│   │   └── research.py             # 业务服务层
│   ├── workflows/research/
│   │   ├── graph.py                # 阶段编排（固定图）
│   │   ├── context.py              # ResearchContext 状态载体
│   │   ├── config.py               # 工作流参数（max_tool_calls 等）
│   │   ├── lang.py                 # 语言指令常量
│   │   └── stages/
│   │       ├── core.py             # intake / plan / retrieve
│   │       ├── pipeline.py         # tool-exec / synthesize / review / persist
│   │       └── tools.py            # 6 种工具注册与实现
│   ├── adapters/
│   │   ├── llm/openai/             # OpenAI 客户端
│   │   ├── market_data/
│   │   │   ├── router.py           # 行情数据路由
│   │   │   ├── akshare/            # AKShare 实现
│   │   │   ├── fmp/                # FMP 实现
│   │   │   └── yfinance/           # yfinance 实现
│   │   └── search/
│   │       ├── exa/                # Exa Search 实现
│   │       └── tavily/             # Tavily 实现
│   └── storage/
│       ├── run_store.py            # InMemory / SQLAlchemy 运行存储
│       ├── db_store.py             # SQLAlchemy 实现
│       └── models.py               # ORM 模型
├── static/
│   └── index.html                  # 前端单页应用
└── tests/                          # 单元 / 集成测试
```

---

## 10. 关键调用链（一次完整请求）

```
用户点击"开始研究"
    │
    │ POST /v1/research/runs
    │ {question, ticker, template, lang}
    ▼
router.py → ResearchService.run(request, deps)
    │
    ├─ ResearchContext 初始化（run_id、question、ticker、lang）
    │
    ├─ graph.execute_workflow(context, deps)
    │     │
    │     ├─ [intake]     生成 run_id，记录请求
    │     ├─ [plan]       LLM → 检索计划 JSON
    │     ├─ [retrieve]   SearchTool × N → EvidenceItem[]
    │     ├─ [tool-exec]  LLM 循环 → 调用工具 → 追加 evidence（最多 3 轮）
    │     ├─ [synthesize] LLM → 结构化报告文本
    │     ├─ [review]     LLM → {passed, feedback}
    │     └─ [persist]    append trace（⚠️ 无实际 IO）
    │
    ├─ 组装 RunResult（report / evidence / trace / providers / ...）
    │
    └─ RunStore.save(run_result)
            │
            └─ 返回 RunResult JSON → 前端渲染
```

---

*文档由 Claude Code 自动生成，基于代码静态分析。如代码变更请同步更新此文档。*
