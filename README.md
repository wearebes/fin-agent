# fin-agent

`fin-agent` 是一个面向金融研究代理的 Python scaffold，已经具备统一配置加载、组合根装配、CLI/API/静态页面入口、可执行 research workflow，以及可切换的内存/SQLite 运行结果存储。

## 当前真实能力边界

- 已实现（以当前源码为准）：
  - 通过 `configs/`、`.env`、环境变量和默认值装配 `AppSettings`
  - 通过 `src/fin_agent/bootstrap/container.py` 统一装配 store、provider adapter、service
  - 通过 `fin-agent research run` 驱动完整研究工作流：
    `intake -> plan -> retrieve -> tool-exec -> synthesize -> review -> persist`
  - 通过 `fin-agent api` 暴露 HTTP API：
    - `GET /healthz`
    - `POST /v1/research/runs`
    - `GET /v1/research/runs/{id}`
    - `GET /v1/research/runs/{id}/trace`
  - 根路径 `/` 已挂载一个静态单页页面（`static/index.html`）
  - OpenAI LLM 调用（plan / tool-exec / synthesize / review）
  - 搜索 adapter：Exa、Tavily
  - 市场数据 adapter：YFinance、AKShare、FMP，并通过 `MarketDataRouter` 做路由/合并
  - 运行结果存储：
    - `InMemoryRunStore`
    - `SQLAlchemyRunStore`，可切到 SQLite 或其他 SQLAlchemy URL
- 还没有闭环的能力：
  - API 认证、限流、租户隔离
  - Streaming / SSE 实时进度推送
  - 后台 Job Queue；当前 `POST /v1/research/runs` 仍是阻塞式
  - 机器可读的 tool schema / function-calling 契约
  - review 失败后的自动重试 / 条件分支
  - 长期记忆、向量检索、历史 run 复用

---

## 架构总览

当前调用链很清楚，主骨架本身是合理的：

```text
CLI / FastAPI
  -> load_settings()
  -> build_container()
  -> ResearchService.run()
  -> execute_workflow()
  -> RunStore.save()
```

各层职责如下：

- `src/fin_agent/bootstrap/settings.py`
  - 唯一配置入口
  - 配置优先级：初始化参数 > 环境变量 > `.env` > `configs/base.yaml` + `configs/environments/{env}.yaml` > 默认值
- `src/fin_agent/bootstrap/container.py`
  - 组合根
  - 负责实例化 `RunStore`、LLM、Search、MarketDataRouter、`ResearchService`
- `src/fin_agent/services/research.py`
  - 服务层入口
  - 承接 request，执行 workflow，组装 `RunResult` 并写入 store
- `src/fin_agent/workflows/research/`
  - workflow 编排与 stage 实现
  - `ResearchContext` 作为一次 run 的内部状态载体
- `src/fin_agent/storage/`
  - `RunStore` 抽象、内存实现、SQLAlchemy 实现、ORM model
- `src/fin_agent/interfaces/api/router.py`
  - 对外 HTTP 契约
- `src/fin_agent/bootstrap/cli.py`
  - CLI 入口与 `doctor` 诊断面

这个分层方式的优点是：

- 配置加载、依赖装配、业务执行、存储、接口边界是分开的
- 后续加 provider、新 stage、新 store 时有明确挂载点
- 现在还没有复杂到必须引入 LangGraph / Celery / Airflow 这种更重的框架

问题不在“有没有分层”，而在“分层之后有没有把闭环做完整”。

---

## 快速启动

### 第一步：创建并激活 conda 环境

```bash
conda env create -f environment.yml
conda activate fin-agent
python -m pip install -e ".[dev]"
```

### 第二步：配置环境变量

```bash
cp .env.example .env
```

然后编辑 `.env`。当前最少要保证默认 LLM 可用：

| 变量                         | 什么时候需要                      | 说明                                                                          |
| ---------------------------- | --------------------------------- | ----------------------------------------------------------------------------- |
| `FIN_AGENT__OPENAI__API_KEY` | 必填                              | 默认 LLM provider 是 OpenAI-compatible 接口；不填则 workflow 启动校验直接失败 |
| `FIN_AGENT__SEARCH__API_KEY` | 当 search provider 选 `exa` 时    | Exa 搜索 key                                                                  |
| `FIN_AGENT__TAVILY__API_KEY` | 当 search provider 选 `tavily` 时 | Tavily 搜索 key                                                               |

这里有一个需要注意的现状：

- `configs/base.yaml` 当前默认 search provider 是 `tavily`
- `.env.example` 里给的是 `exa` 示例

也就是说，你需要让“provider 选择”和“对应 key”保持一致，二选一即可：

```bash
# 方案 A：沿用 .env.example 的 Exa 方案
FIN_AGENT__PROVIDERS__DEFAULT_SELECTION__SEARCH=exa
FIN_AGENT__SEARCH__API_KEY=<set-me>

# 方案 B：沿用 base.yaml 的 Tavily 方案
FIN_AGENT__PROVIDERS__DEFAULT_SELECTION__SEARCH=tavily
FIN_AGENT__TAVILY__API_KEY=<set-me>
```

如果只关心最小跑通，不需要联网搜索，也可以先只填 OpenAI key；这样 market data 仍可运行，但搜索证据可能为空。

如果希望 run 结果落到 SQLite，而不是只存内存，再加一项：

```bash
FIN_AGENT__DATABASE__BACKEND=sql
```

### 第三步：验证配置

```bash
fin-agent doctor
```

输出 JSON，`validation_errors: []` 表示配置正常。如果有缺失的必填项会列出错误。

### 第四步：启动前端（可选）

```bash
cd frontend
npm install          # 首次或依赖变更时执行
npm run dev          # 开发模式，监听 http://localhost:5173
```

> **Windows 用户**：如果 `npm install` 报 ECONNRESET，改用镜像源：
> ```bash
> npm install --registry=https://registry.npmmirror.com
> ```

前端需要后端 API 在运行（`fin-agent api --reload`，默认 `http://127.0.0.1:8000`）。

---

## 日常使用

```bash
# 执行一次研究工作流
fin-agent research run --question "Summarize AAPL positioning" --ticker AAPL

# 启动 HTTP API（开发模式，改代码自动重载）
fin-agent api --reload

# 启动前端开发服务器（另开一个终端）
cd frontend && npm run dev   # → http://localhost:5173

# 构建前端产物
cd frontend && npm run build

# 运行测试
pytest
```

**`research run` 的输出说明：**

- 默认会同步执行完整 workflow，然后一次性返回 `RunResult` JSON
- 如果配置 `FIN_AGENT__DATABASE__BACKEND=sql`，结果会写入 SQLite/SQLAlchemy store
- 如果未配置搜索 key，`retrieve` 阶段的搜索证据可能为空，但市场数据仍会按 provider 能力尽量返回
- 填入有效 OpenAI key 后，`synthesize` 阶段才会生成真实报告

**`fin-agent api` 启动后：**

- `http://127.0.0.1:8000/` - 静态单页 UI
- `http://127.0.0.1:8000/healthz` - 健康检查
- `http://127.0.0.1:8000/docs` - Swagger UI（本地环境默认开启）

---

## 这个架构的不足

这个仓库的主骨架是好的，但目前存在几个比较明确的工程短板：

1. provider 抽象还没有完全闭环
   - 配置层已经有 `providers.default_selection`
   - 但 `container.py` 里 LLM 仍直接写死 `OpenAIClient`
   - `market_data` 的 provider 选择也不是严格按配置切换，而是 `MarketDataRouter` 内部自己做硬编码 fallback 顺序

2. workflow 的失败语义比较脆弱
   - `execute_workflow()` 捕获 stage 异常后，只是在 `trace` 里追加 `"Stage failed with error"`
   - `ResearchService` 再通过 `trace.detail` 里是否包含 `"failed"` 来判断 run 是否失败
   - 这种状态判断依赖自由文本，不够稳，后续一加重试/分支就容易失控

3. `persist` stage 和真实持久化职责不一致
   - workflow 里的 `persist` 目前只追加 trace
   - 真正的 `RunStore.save()` 发生在 `ResearchService.run()` 末尾
   - 这会让“stage 语义”和“实际副作用位置”分离，后面接异步任务或审计日志时容易混乱

4. 输出契约还在丢信息
   - `ResearchContext` 里已经有 `tool_calls`、`review_passed`、`review_feedback`
   - 但最后对外的 `RunResult` 没有这些字段
   - 也没有把真实 retrieval plan 暴露出来
   - 这意味着 API/CLI 能看到的是“结果摘要”，不是一次 run 的完整可审计交付物

5. async 外壳和 sync I/O 混在一起
   - API / service / workflow 都是 async
   - 但搜索和行情 adapter 大多还是同步调用
   - 当前量级下能跑，但一旦并发上来，`POST /v1/research/runs` 会阻塞事件循环，前端也无法拿到真实的 running 进度

6. 文档和配置口径还在漂移
   - `README`、`.env.example`、`configs/base.yaml` 之前已经出现不一致
   - 这种问题短期看只是“文档不好”，长期看会直接把后续开发带偏

如果只问一句“这个架构好不好”，答案是：主分层是对的，但它现在更像一个已经能跑的 MVP 骨架，还不是一个闭环、可扩展、可运维的研究系统。

---

## 开发文档

更详细的目录说明、调用链、配置优先级和扩展边界见 `.claude/docs.md`。
