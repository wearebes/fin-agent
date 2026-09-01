# 用户自带模型 API（2026-08-31）

入口：用户中心 → 模型 API，或助手输入框上方“连接 / 管理 API”。新版已在 `http://127.0.0.1:8001/#/user/models` 启动，使用真实应用工厂与模型客户端，没有替换为模拟供应商。原 8000 服务与内存数据保留；8001 的账户与记录独立，不会自动迁移旧服务数据。**页面和本地服务已验证；用户授权后进行的一次真实请求返回 404 UnsupportedModel，尚未接通模型，不能宣称全部可用。**

## 使用

1. 登录 FinAgent 账户，选择供应商。页面预填基础地址；模型名称需从该供应商控制台复制，豆包也可填对应推理接入点 ID。
2. 填入自己的 API Key，点击“保存并用于研究”。保存本身不会调用模型；保存后输入框清空，界面只显示模型、地址和失效时间。
3. 如需连通性检查，勾选费用提示后点击“测试连接”。只发送一次固定短问题，输出上限 128 token，不自动重试。必须收到非空文本才能通过；HTTP 200、空文本或只有思考块都不算成功。通过仅证明该次文本请求成功，不能证明研报质量或其他模型正常。部分推理模型可能耗尽该短测试预算但未输出文本，应保留失败结果，不自动追加费用。
4. 回到金融助手，确认“研究模型”选择“我的 API”，再提交研究。个人配置未保存、过期或后端未升级会明确失败，不会改用系统密钥。用户仍可主动切换“系统默认”。
5. 不再使用时点“断开并清除密钥”，删除服务端暂存配置。已开始的请求可能继续执行；如需撤销供应商密钥，应到供应商控制台操作。

## 国内与国际接口

| 供应商 | 页面预设基础地址 | 协议及官方依据 |
| --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | Chat Completions；[鉴权说明](https://developers.openai.com/api/reference/overview#authentication) |
| DeepSeek | `https://api.deepseek.com` | [OpenAI 兼容](https://api-docs.deepseek.com/) |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | [百炼区域地址与 Key](https://help.aliyun.com/zh/model-studio/get-api-key/) |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | [OpenAI 兼容](https://docs.bigmodel.cn/cn/guide/develop/openai/introduction) |
| Kimi | `https://api.moonshot.cn/v1` | [OpenAI 兼容](https://platform.kimi.com/docs/overview) |
| 豆包 | `https://ark.cn-beijing.volces.com/api/v3` | 方舟 Chat Completions 兼容入口；模型/接入点以控制台权限为准 |
| Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | [OpenAI 兼容层](https://ai.google.dev/gemini-api/docs/openai) |
| Claude | `https://api.anthropic.com/v1` | [原生 Messages](https://platform.claude.com/docs/en/api/messages/create)，使用独立鉴权与响应解析 |

支持自定义 HTTPS 兼容服务，但域名必须由管理员加入 `runtime.llm_allowed_hosts`，可通过 `FIN_AGENT__RUNTIME__LLM_ALLOWED_HOSTS` JSON 数组覆盖。只接受精确域名与 443 端口；禁止用户信息、查询参数、片段和直接填写补全端点。默认已允许百炼北京、新加坡和美国的共享域名；其他区域或工作空间专属域名需明确加入。国际接口还受网络可达性、区域及账户权限限制，不能宣称所有模型均已真实连通。管理员可沿用现有 `proxy.https`/`proxy.http` 配置受信任代理，不继承任意环境代理，也不跟随上游重定向。

高级设置提供 OpenAI Chat Completions / Anthropic Messages 协议及 `max_tokens` / `max_completion_tokens` 选项。个人接口不强制传入 temperature，使用供应商采样默认值，减少模型间差异；系统接口行为保留。只支持当前文本研究流程，不包含语音、视频或供应商原生联网工具。网页会员、Coding Plan 与通用 API 使用权不等价，用户须按供应商条款选择凭证。

## 安全与兼容

- 按认证账户隔离，一账户一个暂存连接；API Key 使用 SecretStr，仅留在当前服务进程内存，24 小时后失效，访问存储时清理过期项，服务停止后丢失。前端不保存密钥到 localStorage/sessionStorage；设置响应、研究请求/记录不包含密钥。
- 保存后仅切换该账户浏览器的非敏感模型来源偏好，不覆盖 `.env`、系统供应商或其他账户。未登录、非安全网页不能提交密钥；线上必须使用 HTTPS。短测试失败仅返回清理后的错误分类，不回传上游错误正文。
- 上限 1000 个暂存连接。当前方案面向本地单进程运行；多 worker 或需要持久化时，应另行引入受控密钥存储，本轮不引入数据库迁移或额外依赖。退出登录不等于撤销供应商密钥，建议先断开。
- 原研究/账户/行情接口不替换；个人研究使用独立 `/v1/research/personal/stream` 路由，沿用同一套流程和金融数据源。每次研究仍可能包含多次模型和原有检索调用，不能把“自带 Key”理解为全部免费。

## 验收

202 项后端测试通过（最后一轮 13.92 秒），30 项前端测试通过；改动模块 Ruff、TypeScript 检查与前端构建通过。7 个核心 Python 模块 mypy 通过；本机缺少 PyYAML 类型桩，检查时跳过 `import-untyped`，不声称全库严格类型检查通过。新增测试覆盖账户隔离、过期拒绝、错误不泄露密钥、危险地址拒绝、无自动系统回退、所有研究阶段使用个人客户端、两种协议鉴权和 token 参数，以及 HTTP 成功但无有效文本时拒绝通过。

验证分层记录，避免把模拟通过当作真实连通：

| 层级 | 已执行 | 结果与限制 |
| --- | --- | --- |
| 离线自动化 | 真实 `create_app` 生命周期、真实账户注册/保存/删除；协议请求由 MockTransport 或测试替身响应 | 202 项通过；测试环境禁止外网，不是供应商实测 |
| 模拟供应商浏览器操作 | 独立 8765 页面完成假账户/假密钥保存、手动测试、切换 Claude、断开、中英文和 390×844 布局检查 | 保存时模拟调用 0 次；两种协议手动测试各 1 次；不代表真实模型成功 |
| 实际部署 | 8001 使用原应用工厂、原真实客户端和最新 `frontend/dist`；启动、首页、健康及供应商选项接口 | HTTP 200；确认首页引用本轮 JS 构建，浏览器页面错误日志为空 |
| 实际鉴权边界 | 未登录访问个人配置 GET/PUT/DELETE、连接测试 POST、个人研究 POST | 5 项均返回 401，没有触发模型请求 |
| 实际登录后的网页操作 | 尝试创建独立本地验收账户 | 浏览器安全确认拦截了创建操作；未改用其他工具绕过。该部署中的登录后保存/测试流程待用户批准临时账户后执行 |
| 真实供应商请求 | 用户明确授权“调用一次”后，调用项目真实 `OpenAIClient.check_connection`，使用现有方舟配置；未使用模拟响应 | 2026-08-31 20:47:47—20:47:49（北京时间）仅 1 次 POST，最多 128 输出 token、0 次自动重试；HTTP 404，错误码 `UnsupportedModel`，无生成文本及用量信息；未通过 |

实际部署检查发现并修正了两项问题：`ProxyConfig` 未纳入总配置，导致新版启动失败；初次预览配置没有移除旧首页，导致新接口正常但仍显示旧页面。现已补齐配置并构建到正常 `frontend/dist` 目录，使用未改写路由的真实应用重新验证。原 8000 进程仍为 PID 25088，健康检查 200，未重启或清理。

可复核本地 HTTP 结果保存在本轮备份目录的 `real-service-verification.json`，实际服务启动/访问日志为 `real-server.err.log`、`real-server.out.log`。真实供应商请求结果单独保存在本目录 [model-api-live-20260831.json](model-api-live-20260831.json)，不含密钥。此记录只覆盖列明的检查；尚未验证真实模型生成完整研报、全部供应商或金融数据源可达性。

本次实际使用 `https://ark.cn-beijing.volces.com/api/plan/v3` 和项目原配置模型 ID `GLM-5.1`。供应商返回 `UnsupportedModel`，只能确认当前地址/模型组合被拒绝，不能由此断言密钥失效或所有方舟模型不可用。火山引擎[模型接入示例](https://developer.volcengine.com/articles/7632697946764476452)列出的模型 ID 为小写 `glm-5.1`；大小写及当前套餐的模型支持范围需要核对，尚未通过第二次请求确认原因。未修改项目密钥、地址或模型配置，未追加调用，也未绕过临时账户创建的确认限制。响应未返回 token 用量，不能据此断言本次费用为零。

主要文件：`ModelSettingsPage.tsx`、`api/models.ts`、`model_router.py`、`services/model_connections.py`、`adapters/llm/anthropic.py`。本轮修改前备份和验证日志位于 `C:\Users\XCH\AppData\Local\Temp\fin-agent-api-settings-before-v4dsym9q`。最新构建写入此前不存在的 `frontend/dist`，未修改原 `static` 首页。后续正常启动可使用项目原 CLI 的 `api --port 8001`，应先确认该端口空闲；不重复启动或停止承载用户内存数据的进程。
