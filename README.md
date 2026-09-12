# FinAgent

FinAgent 是一个本地运行的金融研究与量化策略分析工具。用户可以接入自己的模型 API，提交后台研究任务，生成带行情、财务、新闻和来源的网页研报；量化模块使用真实历史收盘价评估常见策略，并检查数据泄漏、参数敏感度、交易成本和市场状态依赖。

## 功能

- 金融研究：`计划 → 取数 → 补充工具 → 撰写 → 复核 → 保存`
- 后台任务：页面关闭后继续执行，支持进度、历史和失败重试
- 图文研报：行情、回撤、年度三张财务报表、关键指标、新闻与来源
- 用户自带 API：OpenAI、DeepSeek、通义千问、GLM、Kimi、豆包、Gemini、Claude 及受信任的兼容接口
- 量化策略：均线、突破、均值回归、RSI、动量、布林带和自定义规则
- 数据源：Yahoo Finance、AKShare、东方财富、新浪财经，可选 FMP、Tavily 和 Exa
- 本地账户与 SQLite：研究任务和报告按账户保存；API Key 不落盘

完整的研报口径与运行边界见 [后台研究与图文研报](docs/research-reports.md)。

## 目录

```text
src/fin_agent/
  adapters/      模型、搜索和市场数据接入
  bootstrap/     配置、依赖装配和应用启动
  domain/        数据模型与枚举
  interfaces/    HTTP 与本地服务入口
  services/      研究任务、账户和策略分析服务
  skills/        内置研究技能
  storage/       SQLite/SQLAlchemy 存储
  workflows/     金融研究流程
frontend/        React/Vite 前端
tests/           后端测试
docs/            当前使用与能力说明
configs/         分环境配置
alembic/         数据库迁移
```

`output/`、`tmp/`、`var/` 和前端构建产物均为本地文件，不进入 Git。

## 安装

要求 Python 3.12+ 和 Node.js 20+。

```bash
conda env create -f environment.yml
conda activate fin-agent
python -m pip install -e ".[dev]"
cd frontend
npm install
npm run build
cd ..
```

复制环境变量示例：

```bash
cp .env.example .env
```

默认搜索供应商是 Tavily。若使用 Exa，需要同时设置供应商名称和对应 Key；不配置搜索 Key 时，行情和可用的 A 股公开新闻仍可运行。

## 启动

Windows 本地桌面使用：

```text
双击 start_silent.vbs
```

开发模式：

```bash
fin-agent api --reload
```

访问：

- 应用：`http://127.0.0.1:8000/`
- 健康检查：`http://127.0.0.1:8000/healthz`
- API 文档：`http://127.0.0.1:8000/docs`

也可以单独启动前端开发服务器：

```bash
cd frontend
npm run dev
```

## 用户自己的模型 API

登录后进入“模型连接设置”，选择供应商，填写 Base URL、Model ID 和 API Key。保存仅把密钥暂存在服务端内存，24 小时后或服务重启时失效。网页会员、Coding Plan 和 API 额度通常相互独立；模型名称和可用额度以供应商控制台为准。

本地服务允许的常用地址已在设置页预置。自定义地址必须使用 HTTPS，并由管理员加入 `FIN_AGENT__RUNTIME__LLM_ALLOWED_HOSTS`。

## 验证

```bash
pytest
ruff check .
cd frontend
npm run typecheck
npm run build
npm test
```

量化结果基于历史数据与简化成交假设，研报依赖公开数据和所选模型，均不构成投资建议。
