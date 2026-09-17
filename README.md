# FinAgent

> 一个在本地运行、重视数据来源和计算过程的金融研究工具

FinAgent 把 AI 分析、行情、财务报表、新闻检索和策略回测放在同一个界面里。你可以直接提出一个金融问题，系统会查找数据、整理分析，并生成带图表和来源的报告。

这个项目不只追求“能回答”，也重视答案能不能核对。图表只使用实际取得的数据，缺少的信息会直接说明；财务指标按固定公式计算，策略回测也会检查未来数据泄漏、交易成本、参数变化和样本外表现。

## 下载与使用（Windows）

可以从 GitHub 下载使用，但目前还不是免安装软件。第一次使用需要安装 Python 和 Node.js，并运行一次安装命令；以后只需双击启动文件。

### 第一次使用

1. 在 GitHub 页面点击绿色的 `Code` 按钮，再点击 `Download ZIP`；也可以直接[下载最新版 ZIP](https://github.com/wearebes/fin-agent/archive/refs/heads/main.zip)。
2. 解压文件，并安装 Python 3.12 或更高版本、Node.js 20 或更高版本。
3. 打开解压后的文件夹，在空白处右键选择“在终端中打开”，依次运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .

cd frontend
npm install
npm run build
cd ..

Copy-Item .env.example .env
```

4. 双击 `start_silent.vbs`，等待几秒后在浏览器打开 `http://127.0.0.1:8000/`。

以上安装只需完成一次。以后进入项目文件夹，双击 `start_silent.vbs` 即可启动。

## 能做什么

### 金融研究

- 研究流程：`制定计划 → 获取数据 → 补充检索 → 撰写报告 → 复核结论 → 保存结果`
- 后台任务：页面关闭后继续执行，支持进度查看、历史报告和失败重试
- 图文报告：展示行情、回撤、年度三张财务报表、关键指标、新闻线索、来源和数据缺口
- 模型接入：支持 OpenAI、DeepSeek、通义千问、GLM、Kimi、豆包、Gemini、Claude 及受信任的兼容接口

### 量化策略分析

- 内置均线、突破、均值回归、RSI、动量、布林带和自定义规则
- 使用真实历史收盘价，信号只读取前一交易日及更早的数据，并在下一交易日收盘成交
- 检查交易成本、三折滚动样本外表现、参数敏感度、下行风险和不同市场状态下的表现
- 输出收益、波动率、最大回撤、夏普比率、Sortino 比率和 Calmar 比率等指标

### 数据与本地使用

- 数据源：Yahoo Finance、AKShare、东方财富、新浪财经，可选 FMP、Tavily 和 Exa
- 本地账户与 SQLite：研究任务和报告按账户隔离保存
- API Key 仅暂存在服务端内存，24 小时后或服务重启时失效，不写入数据库或浏览器存储
- Windows 可通过桌面启动脚本运行，也支持前后端开发模式

## 如何保证结果可信

- 报告图表使用取数阶段保存的真实数据，不从模型生成的文字中猜数字
- 财务比率保留来源和计算方法，不混用来源、币种或报告期不一致的报表字段
- 缺少预测现金流、折现率、终值增长率等关键依据时，不生成 DCF 目标价
- 遇到异常价格、日期缺口、数据冲突或外部服务失败时，系统会明确报错，不会自行补数或删数
- 模型调用失败时，已经取得的数据和量化结果仍会保留，也不会自动更换模型或重复产生费用

更完整的方法说明、数据口径和已知边界见 [后台研究与图文研报](docs/research-reports.md)。

## 技术栈

- 后端：Python 3.12、FastAPI、Pydantic、SQLAlchemy、SQLite、Alembic
- 前端：React、TypeScript、Vite、TanStack Query、Zustand
- 数据与模型：pandas、yfinance、AKShare、OpenAI 兼容接口
- 测试与质量：pytest、Node.js Test Runner、Ruff、mypy

## 开发模式

完成首次安装后，可以运行：

```powershell
.\.venv\Scripts\fin-agent.exe api --reload
```

- 应用：`http://127.0.0.1:8000/`
- 健康检查：`http://127.0.0.1:8000/healthz`
- API 文档：`http://127.0.0.1:8000/docs`

如需单独调试前端：

```powershell
cd frontend
npm run dev
```

## 模型连接

登录后进入“模型连接设置”，填写供应商、Base URL、Model ID 和 API Key。网页会员、Coding Plan 与 API 额度通常相互独立，实际模型名称和可用额度以供应商控制台为准。

常用服务地址已在设置页预置；自定义地址必须使用 HTTPS，并由管理员加入 `FIN_AGENT__RUNTIME__LLM_ALLOWED_HOSTS`。未配置搜索 Key 时，行情和可用的 A 股公开新闻仍可运行。

## 项目结构

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
docs/            使用说明与方法边界
configs/         分环境配置
alembic/         数据库迁移
```

`output/`、`tmp/`、`var/` 和前端构建产物均为本地文件，不进入 Git。

## 验证

运行测试前先安装开发依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .

cd frontend
npm run typecheck
npm run build
npm test
```

## 使用范围

FinAgent 目前适合在个人电脑上运行，还不是面向大量用户的在线服务。研究报告依赖公开数据和用户选择的模型；量化结果基于历史数据和简化的成交假设，不代表未来表现，也不构成投资建议。

## License

[MIT](LICENSE)
