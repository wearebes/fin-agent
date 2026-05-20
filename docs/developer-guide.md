# fin-agent 开发文档

## 1. 项目定位

`fin-agent` 现在是一个“可运行的架构骨架”，不是完整的金融研究代理产品。

当前代码已经完成的事情：

- 用统一入口加载配置
- 用统一容器装配运行时对象
- 暴露 CLI 和 FastAPI API
- 生成 research workflow 的阶段计划
- 将运行结果保存在内存中，便于 API 查询 trace

当前还没有完成的事情：

- 真实 OpenAI / Exa / YFinance client
- 真实外部调用与结果汇总
- 数据库读写
- 面向生产的任务编排、重试、审计和监控

阅读和扩展这个仓库时，应该默认把它理解为 scaffold，而不是“已经能跑实盘研究”的代理。

## 2. 目录职责

### `configs/`

- 保存全局运行时配置。
- `base.yaml` 是基础配置。
- `configs/environments/{env}.yaml` 是按环境覆盖的配置。
- 这里只放应用级运行时状态，不放 provider 代码实现。

### `src/fin_agent/bootstrap/`

- 启动层，是整个仓库最重要的入口。
- `settings.py` 负责统一读取 YAML、`.env`、环境变量和默认值。
- `container.py` 负责运行时装配和基础校验。
- `cli.py` 定义命令行入口。
- `app.py` 定义 FastAPI 应用和生命周期。

### `src/fin_agent/adapters/`

- 预留给外部 provider 适配层。
- 当前只有 `openai`、`exa`、`yfinance` 的配置模型。
- 这里现在还没有真实 HTTP client、SDK 调用或 provider response 解析逻辑。

### `src/fin_agent/domain/`

- 保存领域常量和公共数据结构。
- `constants.py` 定义环境名、provider 名、workflow 名和运行状态。
- `types.py` 定义 CLI/API 共用的 request/response schema。

### `src/fin_agent/interfaces/`

- 暴露对外接口。
- 当前只有 `interfaces/api/router.py`，负责 FastAPI 路由。

### `src/fin_agent/services/`

- 编排应用层行为。
- `research.py` 当前负责把请求转换成一个 scaffold 级别的运行结果。
- 它会生成阶段计划、提示当前 provider 选择，并把结果保存到 `RunStore`。

### `src/fin_agent/storage/`

- 保存运行结果存储接口。
- 当前只有 `InMemoryRunStore`，生命周期跟进程一致，重启后数据丢失。

### `src/fin_agent/workflows/`

- 保存 workflow 相关配置和流程结构。
- `workflows/research/config.py` 定义 research workflow 的限制参数。
- `workflows/research/graph.py` 当前只负责生成阶段列表，不执行真实图调度。

### `tests/`

- 保存接口和配置装配测试。
- 当前测试覆盖重点是：
  - 配置加载与优先级
  - `.env.example` 与 schema 同步
  - CLI/API 基本可用
  - scaffold 语义不冒充真实 provider 调用

## 3. 两条主调用链

### `fin-agent research run`

调用链如下：

1. `bootstrap/cli.py:research_run`
2. `load_settings()` 读取配置
3. `build_container()` 做运行时校验并装配 `ResearchService`
4. `ResearchService.run()` 生成阶段计划和 scaffold trace
5. `InMemoryRunStore.save()` 保存结果
6. CLI 输出 `RunResult` JSON

这条链路当前不会做真实搜索、真实模型推理或真实行情查询。

### `fin-agent api`

调用链如下：

1. `bootstrap/cli.py:api`
2. `uvicorn` 启动 `bootstrap.app:create_default_app`
3. `create_app()` 在 lifespan 中加载 settings 和 container
4. `interfaces/api/router.py` 注册 `/healthz`、`/v1/research/runs`、`/trace`
5. POST `/v1/research/runs` 最终调用 `ResearchService.run()`
6. GET `/v1/research/runs/{run_id}` 和 `/trace` 从 `InMemoryRunStore` 读取结果

API 和 CLI 共用同一套配置装配与 service 逻辑，所以它们的 scaffold 语义应该保持一致。

## 4. 配置优先级

真实优先级以 `AppSettings.settings_customise_sources()` 为准：

1. 初始化参数
2. 进程环境变量
3. `.env`
4. 分层 YAML
5. 模型默认值

具体说明：

- CLI 里 `--env` 最终会以初始化参数或环境变量形式指定 `app.environment`。
- YAML 由 `configs/base.yaml` 和 `configs/environments/{env}.yaml` 深度合并。
- provider 默认值和 workflow 默认值定义在各自模块的 `BaseModel` 配置类中。
- 只有 `bootstrap/settings.py` 可以直接读取环境变量和 YAML，其它层只能接收解析后的 settings。

## 5. 当前真实实现与占位层边界

这部分是理解仓库的关键。

### 已真实接通的部分

- 配置树解析
- CLI 命令注册
- FastAPI 应用启动
- request/response schema
- research workflow 阶段计划生成
- 内存级运行结果存取

### 仍是占位或扩展位的部分

- `adapters/llm/openai/`：只有配置，没有真实 client
- `adapters/search/exa/`：只有配置，没有真实搜索调用
- `adapters/market_data/yfinance/`：只有配置，没有真实行情拉取
- `services/research.py`：只生成计划化结果，不做真实 research execution
- `database.*` 配置：当前未接入 SQLAlchemy engine/session
- 某些 feature flag 和 provider 选择项目前主要是结构预留，不代表所有字段都已经产生行为

因此，`RunResult.status == "completed"` 现在表示“scaffold 流程已完成”，不是“真实研究任务已完成”。

## 6. 后续扩展应该从哪里下手

如果以后要接真实 provider，建议保持现有分层，并沿着下面的落点扩展。

### 接真实 LLM

- 在 `src/fin_agent/adapters/llm/openai/` 下加入真实 client 和调用封装。
- 把模型名、超时、base URL、key 继续放在现有 `OpenAIConfig`。
- 在 `bootstrap/container.py` 中装配 client。
- 在 `ResearchService` 或后续 workflow executor 中调用，而不是在 CLI/API 层直接调用。
- 在 `tests/` 中补 adapter 单测和 service 层伪造依赖测试。

### 接真实搜索

- 在 `src/fin_agent/adapters/search/exa/` 下加入搜索 client。
- 继续使用 `ExaSearchConfig` 管理 `api_key`、`max_results`、`include_text`。
- 由 service/workflow 层决定何时触发搜索，而不是路由层。

### 接真实市场数据

- 在 `src/fin_agent/adapters/market_data/yfinance/` 下加入拉取逻辑。
- 将历史区间、超时等配置继续保留在 `YFinanceConfig`。
- 由 research workflow 在需要 ticker 上下文时调用。

### 接数据库持久化

- 优先从 `storage/` 抽象开始，新增基于 SQLAlchemy 的 `RunStore` 实现。
- 再在 `bootstrap/container.py` 中按配置决定注入哪种 store。
- API 层不应该感知底层存储类型变化。

## 7. 推荐阅读顺序

第一次接手这个仓库，建议按下面顺序读代码：

1. `README.md`
2. `docs/developer-guide.md`
3. `src/fin_agent/bootstrap/cli.py`
4. `src/fin_agent/bootstrap/settings.py`
5. `src/fin_agent/bootstrap/container.py`
6. `src/fin_agent/services/research.py`
7. `src/fin_agent/interfaces/api/router.py`
8. `tests/`

这个顺序能最快看清“入口在哪里、真实行为在哪里、哪些只是留位”。

## 8. 常用命令

```bash
conda env create -f environment.yml
conda activate fin-agent
python -m pip install -e ".[dev]"
cp .env.example .env
```

```bash
fin-agent doctor
fin-agent doctor --write-env-example .env.example
fin-agent research run --question "Summarize AAPL positioning" --ticker AAPL
fin-agent api --reload
pytest
```

如果命令输出里出现 scaffold 提示语，说明当前行为符合预期；如果你看到代码声称已经做了真实 provider 调用，但仓库里并没有对应 adapter 实现，那就是需要继续补齐的空位。
