# 金融智能体页面改良建议（2026-08-31）

本文记录最初的调研结论；调研阶段未发送研究请求、未调用模型或金融数据接口。随后经用户授权，已实施任务引导、证据阅读、连续追问等改良，具体改动与验收边界见 [实施记录](agent-ui-implementation-20260831.md)。下文的“当前”描述调研时的基线状态。

## 参考项目

Stars 为本次 GitHub REST API 查询快照，仅用于了解项目规模，不是效果排名。下面借鉴的是交互和实现思路，不引入这些项目的运行框架。

| 项目 | Stars | 直接参考点 | 适配边界 |
| --- | ---: | --- | --- |
| [Dexter](https://github.com/virattt/dexter) | 27,558 | 有限轮次上下文、工具进度事件 | 当前参考以终端交互为主；不照搬其额外模型摘要调用 |
| [GPT Researcher](https://github.com/assafelovic/gpt-researcher) | 29,213 | 来源卡片、正文复制、基于报告的追问 | 复用交互思路，继续使用现有 React/Vite；无需迁移 Next.js |
| [TradingAgents-CN](https://github.com/hsliuping/TradingAgents-CN) | 31,488 | 股票与市场提示、研究日期/深度的显式选择 | 前端是专有许可，仅作产品对照，不复制、改编或移植其前端代码 |

源码依据：[Dexter 上下文](https://github.com/virattt/dexter/blob/ecaed3011f24ea24ef687ab536aa7f22f7294038/src/utils/in-memory-chat-history.ts)、[进度通道](https://github.com/virattt/dexter/blob/ecaed3011f24ea24ef687ab536aa7f22f7294038/src/utils/progress-channel.ts)；[GPT Researcher 来源](https://github.com/assafelovic/gpt-researcher/blob/6f998577d547b1e54ec662dac63583aa11e3b84b/frontend/nextjs/components/ResearchBlocks/Sources.tsx)、[报告追问](https://github.com/assafelovic/gpt-researcher/blob/6f998577d547b1e54ec662dac63583aa11e3b84b/frontend/nextjs/components/ResearchBlocks/ChatInterface.tsx)、[正文操作](https://github.com/assafelovic/gpt-researcher/blob/6f998577d547b1e54ec662dac63583aa11e3b84b/frontend/nextjs/components/ResearchBlocks/Report.tsx)；[TradingAgents-CN 单股分析](https://github.com/hsliuping/TradingAgents-CN/blob/74783e8817d6cf6de29867880631cc555153f36b/frontend/src/views/Analysis/SingleAnalysis.vue)、[前端许可](https://github.com/hsliuping/TradingAgents-CN/blob/74783e8817d6cf6de29867880631cc555153f36b/frontend/LICENSE)。

## 低成本先做

1. **首页增加四张研究任务卡**：财报解读、盈利与现金流、公司对比、新闻与风险。点击只填入可编辑的问题示例，不直接发请求；保留自由输入。标的代码增加常见格式提示，时间范围先明确写入问题，不把它包装成已经实现的历史时点过滤。当前 `template` 字段尚未驱动不同工作流，不能只增加下拉框就宣称多种研究模式已生效。涉及 `ChatView.tsx`、`Composer.tsx`、`i18n.ts`。

2. **结果分为报告、数据与来源、执行记录**：报告正文优先，运行编号、环境和供应商收进执行记录；搜索证据显示标题和可点击原始链接，财报 JSON 按实际返回的财年、季度、指标展示表格。缺失日期、币种和单位明确标为未提供，不能推断或伪造。第一版保留原始证据展开入口，不为了做卡片丢失数据。涉及 `AssistantResult.tsx`、`ResearchProcessPanel.tsx`；可选的结构化来源字段可后续向下兼容添加。

3. **先补报告交付和会话整理**：复制正文、下载 Markdown、浏览器打印，避免先引入复杂 PDF 引擎。用首条问题生成会话标题，不额外调用模型；添加本地会话搜索。文档导出也应保留未通过审查的提示和来源。

4. **统一业务失败的展示与重试**：`ChatView.tsx:64` 当前在 HTTP 请求成功返回时固定把消息写为 completed；但 `result.status` 可能是 failed。现有 `AssistantResult` 会显示失败警告，因此并非页面完全隐藏失败；问题在于这种失败进入了另一条展示路径，没有网络错误时的重试入口。改动必须同时保留失败报告和证据，不能只改消息状态导致正文不再渲染。重复提交仍需受运行状态限制，不自动重试付费研究。

以上改动不需要新增模型调用或替换数据接口。建议首轮优先完成第 1、2、4 项，第 3 项可同批做轻量版本。

## 需要后端配合

- **真正支持连续追问，优先级最高**：`api/research.ts` 只提交本次 question、ticker、template、lang，历史消息停留在浏览器。用户问“它的现金流呢”时，后端没有可靠的前文。先增加可选且有长度上限的上下文，限定同一会话和最近少量轮次，不把全部报告逐次拼回；后续区分“基于已有报告追问”和“重新联网研究”。复用报告/证据时明确数据日期及未更新行情，不能把旧结果当作实时数据。与旧客户端保持兼容，避免新增逐轮模型摘要调用。
- **真实进度而非模拟百分比**：当前 API 等待整个工作流结束才返回，运行中仅有转圈。先展示真实等待时间，并说明刷新会中断前端等待；阶段进度随后通过可选 SSE 接口发送规划、检索、生成、审查等执行事件，旧 POST 接口保留。现有 GET trace 不是实时进度接口，单纯前端轮询不能补齐。只展示执行摘要，不包装为模型隐藏思维。
- **停止按钮必须说明边界**：AbortController 只能保证浏览器停止等待，不保证后端和供应商停止计费。真正取消需要后端在阶段和工具调用之间检查取消信号；未实现前不能声称点击停止就不再消耗。

## 推荐页面结构与验收

首页保留左侧项目/会话，中央从大面积空白改为任务卡和研究范围说明，底部保留输入框。生成后正文保持主阅读区，数据与来源、执行记录按需展开，避免默认堆满调试字段。

验收应使用离线固定返回值：任务卡不发网络请求；旧会话可读；来源 URL 只允许安全协议；同一会话追问能识别标的、不同会话不串上下文；业务失败仍能看报告和重试；进度和数据日期不编造。不要为了展示效果新增多智能体团队、行情大屏或没有后端功能的深度/实时状态开关。
