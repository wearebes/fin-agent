# 金融智能体首页改良实施记录（2026-08-31）

代码改良与离线验收已完成，未新增依赖、替换金融数据接口、修改密钥或迁移数据库。主前端仍使用 localhost:5173；8000 端口的原后端尚未重启，因此新增流式进度和连续追问尚未在该进程启用。

后续更新：用户已明确将四个首页任务入口合并，现改为统一助手与六类问题示例，组件为 `ResearchExamples.tsx`；下方四张卡片为上一版实施快照。量化扩展及最新演示见 [使用指南](unified-agent-quant-guide-20260831.md)。

## 改了什么

| 优先级 / 资产 | 实现位置 | 结果与参考 |
| --- | --- | --- |
| 立刻可改：任务入口 | `ResearchTasks.tsx`、`Composer.tsx` | 四张中英文任务卡，仅填入可编辑示例，不自动提交；保留自由输入 |
| 立刻可改：证据阅读 | `AssistantResult.tsx`、`EvidencePanel.tsx` | 报告、数据与来源、执行记录分区；安全来源链接、按财年展示原始数值、原始证据可展开；参考 GPT Researcher 的来源与报告组件 |
| 立刻可改：报告交付 | `lib/research.ts`、`AssistantResult.tsx` | 复制与下载 Markdown 包含报告、原始问题、来源和失败警告；提供浏览器打印入口，无 PDF 引擎依赖 |
| 立刻可改：会话整理 | `workspace.ts`、`Sidebar.tsx` | 首问自动命名、本地搜索、各会话草稿保留；合并删除后的重复导航；运行中禁止删除对应会话或项目 |
| 立刻可改：失败处理 | `ChatView.tsx`、`MessageBubble.tsx` | 按业务状态判断失败，保留失败报告与证据；旧记录的错误状态也可重试；保存当时上下文，手动重试不混入后续对话 |
| 小幅改造：连续追问 | `ResearchRequest.history`、`context.py`、`lib/research.ts` | 最多携带本会话最近 3 次成功研究，每轮问题 1000 字符、报告 4000 字符、代码 64 字符；不新增摘要调用；参考 Dexter 的有限历史 |
| 小幅改造：真实进度 | `graph.py`、`router.py`、`api/research.ts`、`ResearchProgress.tsx` | 新增可选 SSE 端点，实际阶段事件与耗时；旧 POST 和查询接口保留；参考 Dexter 进度事件思路 |
| 小幅改造：排版 | `main.tsx`、`research.css` | 统一样式加载顺序、缩小短屏首页留白；手机顶部两行布局；表格横向滚动、导出专用样式 |

本次为轻量适配，未移植开源框架或前端代码。可复用资产的来源、Stars 快照及许可边界见 [调研记录](agent-ui-review-20260831.md)。原权限、Markdown 图文渲染、量化入口均保留；截至本次首页迭代，量化页面仍是“即将上线”。用户随后授权的本地量化功能另见 [量化雏形记录](quant-prototype-20260831.md)，尚不属于完整量化引擎或实盘系统。

## 关键兼容与成本边界

- `history` 默认空列表，无历史时原问题原样进入工作流；旧请求和旧存储记录不需要迁移。历史只是辅助理解的非可信上下文，当前问题和显式代码优先，金融结论仍需新检索证据。
- 原有检索、模型供应商和阶段调用方式保持不变。关联历史会增加输入长度；每次追问仍执行研究，不能称为免费问答。本次测试仅使用固定假数据和替身服务，没有调用付费模型或金融数据接口。
- 流式端点不支持时，仅 404/405 且无历史可回退到旧 POST；500、业务失败或断流不自动重发。有历史而后端过旧时明确报错，避免静默丢弃上下文后执行错误研究。
- SSE 是进度通道，不是持久任务队列。刷新会中断前端等待，后端会取消后续阶段；已进入同步供应商 SDK 的请求可能继续，不能保证停止计费。本轮没有添加“保证停止”的按钮。
- 表格不猜测币种、单位或数据时点；未识别的证据保留原文。复制/Markdown 保存全部证据摘要，打印侧重正文和可读来源表，隐藏调试及原始 JSON。未新增图表生成能力。

核心兼容字段：

```python
class ResearchTurn(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    answer: str = Field(..., max_length=4000)
    ticker: str | None = Field(default=None, max_length=64)

# ResearchRequest 新增字段，其他字段与旧接口保留。
history: list[ResearchTurn] = Field(default_factory=list, max_length=3)
```

完整可运行实现位于 `src/fin_agent/domain/types.py`；SSE 位于 `src/fin_agent/interfaces/api/router.py`，前端请求入口为 `frontend/src/api/research.ts`。

## 验收证据

- Python 全量离线测试 **173 项通过**；改动涉及的研究工作流、服务和 API 通过 Ruff、mypy 检查。
- 前端 **17 项测试通过**，TypeScript 检查与 Vite 构建通过。包含 UTF-8/CRLF 分块事件、断流不重复研究、旧后端回退、历史上限与隔离、失败导出、旧记录兼容、草稿与存储恢复。
- 使用独立的 8765 端口测试服务及固定金融数据验收页面，未对 8000/5173 发送研究请求。任务卡点击后的研究请求数为 0；首次研究、一次追问、独立会话失败、手动重试共 4 次测试请求，历史条数分别为 **0、1、0、0**；重试请求与原失败请求内容完全一致。
- 浏览器确认实际阶段显示、重复提交禁用、失败报告保留、原始数值表格与来源链接、中文/英文切换、搜索、草稿刷新恢复，以及桌面 1280×720 和手机 390×844 排版；测试页面控制台未发现 error。移动视口验收后已恢复。
- 复制/Markdown 的内容经过自动测试；系统打印对话框和最终 PDF 文件尚未人工验收，不将其列为已通过。真实供应商连通性、模型研究质量与跨浏览器打印兼容性不在本次离线结论内。

复查命令（在已安装本项目依赖的环境中）：

```powershell
python -m pytest -q --tb=short
python -m ruff check src/fin_agent/domain/types.py src/fin_agent/interfaces/api/router.py src/fin_agent/services/research.py src/fin_agent/workflows/research tests/test_research_interaction.py
python -m mypy src/fin_agent/workflows/research src/fin_agent/services/research.py src/fin_agent/interfaces/api/router.py --follow-imports=silent
cd frontend
node --test tests/*.test.cjs
npm run typecheck
npm run build
```

## 正式进程启用前的确认

只读检查确认当前配置为 `storage_backend=memory`；原后端健康检查正常，但 OpenAPI 尚无 `/v1/research/stream`。在无法确认内存账户和研究记录是否可丢弃的情况下，未停止或替换它，也没有擅自切换到新内存进程。需要用户确认可重启，或先安排可验证的数据保全方案；浏览器会话记录和服务端内存记录是两套不同的存储。

后续架构升级再处理：服务端持久任务、会话/研究记录的用户归属鉴权、证据结构化与图表、完整量化后端。现有研究接口仍未补齐用户归属隔离，不应直接开放到公网。

参考来源：[Dexter 上下文](https://github.com/virattt/dexter/blob/ecaed3011f24ea24ef687ab536aa7f22f7294038/src/utils/in-memory-chat-history.ts)、[Dexter 进度](https://github.com/virattt/dexter/blob/ecaed3011f24ea24ef687ab536aa7f22f7294038/src/utils/progress-channel.ts)、[GPT Researcher 来源](https://github.com/assafelovic/gpt-researcher/blob/6f998577d547b1e54ec662dac63583aa11e3b84b/frontend/nextjs/components/ResearchBlocks/Sources.tsx)、[GPT Researcher 报告](https://github.com/assafelovic/gpt-researcher/blob/6f998577d547b1e54ec662dac63583aa11e3b84b/frontend/nextjs/components/ResearchBlocks/Report.tsx)、[FastAPI StreamingResponse](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)、[MDN SSE](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)。
