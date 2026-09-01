import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Cable, Check, FlaskConical, Unplug } from 'lucide-react'
import { disconnectModel, getModelAccess, getModelConnection, modelConnectionOptions, saveModelConnection, testModelConnection } from '../../api/models'
import type { ModelAccess } from '../../api/models'
import type { ModelConnection, ModelProtocol, TokenParameter } from '../../api/models'
import { useUserStore } from '../../store/user'
import { useWorkspace } from '../../store/workspace'
import LocalCodexPanel from './LocalCodexPanel'

const presets = [
  { id: 'openai', name: 'OpenAI', url: 'https://api.openai.com/v1' },
  { id: 'deepseek', name: 'DeepSeek', url: 'https://api.deepseek.com' },
  { id: 'qwen', name: '通义千问 / Qwen', url: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  { id: 'zhipu', name: '智谱 / GLM', url: 'https://open.bigmodel.cn/api/paas/v4' },
  { id: 'kimi', name: 'Kimi', url: 'https://api.moonshot.cn/v1' },
  { id: 'doubao', name: '豆包 / Doubao', url: 'https://ark.cn-beijing.volces.com/api/v3' },
  { id: 'gemini', name: 'Google Gemini', url: 'https://generativelanguage.googleapis.com/v1beta/openai' },
  { id: 'claude', name: 'Anthropic Claude', url: 'https://api.anthropic.com/v1' },
]

export default function ModelSettingsPage() {
  const userId = useUserStore((s) => s.user?.id)
  return <ModelSettingsForm key={userId ?? 'guest'} />
}

function ModelSettingsForm() {
  const user = useUserStore((s) => s.user)
  const setSource = useUserStore((s) => s.setModelSource)
  const lang = useWorkspace((s) => s.lang)
  const text = (zh: string, en: string) => lang === 'zh' ? zh : en
  const [provider, setProvider] = useState('openai')
  const [baseUrl, setBaseUrl] = useState(presets[0].url)
  const [model, setModel] = useState('')
  const [protocol, setProtocol] = useState<ModelProtocol>('openai')
  const [tokenParameter, setTokenParameter] = useState<TokenParameter>('max_completion_tokens')
  const [apiKey, setApiKey] = useState('')
  const [allowedHosts, setAllowedHosts] = useState<string[]>([])
  const [connection, setConnection] = useState<ModelConnection | null>(null)
  const [ready, setReady] = useState(false)
  const [access, setAccess] = useState<ModelAccess | null>(null)
  const [busy, setBusy] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [testConsent, setTestConsent] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const securePage = window.isSecureContext

  useEffect(() => {
    let active = true
    async function load() {
      try {
        const options = await modelConnectionOptions()
        const available = await getModelAccess().catch(() => null)
        const result = user ? await getModelConnection() : { connection: null }
        if (!active) return
        setAllowedHosts(options.allowed_hosts)
        setAccess(available)
        setConnection(result.connection)
        if (result.connection) {
          const saved = result.connection
          setBaseUrl(saved.base_url); setModel(saved.model); setProtocol(saved.protocol)
          setTokenParameter(saved.token_parameter)
          setProvider(presets.find((item) => item.url === saved.base_url)?.id ?? 'custom')
        }
        setReady(true)
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : String(cause))
      }
    }
    void load()
    return () => { active = false }
  }, [user?.id])

  const edited = () => { setDirty(true); setNotice(''); setError(''); setTestConsent(false) }
  const selectProvider = (id: string) => {
    setProvider(id)
    setBaseUrl(presets.find((item) => item.id === id)?.url ?? '')
    setProtocol(id === 'claude' ? 'anthropic' : 'openai')
    setTokenParameter(id === 'openai' ? 'max_completion_tokens' : 'max_tokens')
    setModel(''); setApiKey(''); edited()
  }
  const save = async () => {
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await saveModelConnection({
        base_url: baseUrl.trim(), model: model.trim(), api_key: apiKey.trim(), protocol, token_parameter: tokenParameter,
      })
      setConnection(result.connection); setSource('personal'); setDirty(false); setTestConsent(false)
      setNotice(text('已暂存并选为研究模型，尚未测试连通性。', 'Saved and selected for research; connectivity is not yet tested.'))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setApiKey(''); setBusy(false)
    }
  }
  const test = async () => {
    setBusy(true); setError(''); setNotice(''); setTestConsent(false)
    try {
      await testModelConnection()
      setNotice(text('接口已响应。短测试不代表研究质量或完整功能通过。', 'The API responded. This short check does not validate research quality or all model features.'))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally { setBusy(false) }
  }
  const disconnect = async () => {
    setBusy(true); setError(''); setNotice('')
    try {
      await disconnectModel()
      setConnection(null); setApiKey(''); setSource(access?.system_model === false ? 'personal' : 'default'); setTestConsent(false)
      setNotice(text('已删除服务端暂存密钥。已开始的请求不保证立即停止。', 'The stored key was removed. Requests already in progress may still finish.'))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally { setBusy(false) }
  }

  return <div className="user-page"><div className="user-page-card model-settings-card">
    <div className="user-page-icon"><Cable size={25} /></div>
    <h2>{text('模型连接设置', 'Model connection settings')}</h2>
    <p className="user-page-subtitle">{access?.local_codex
      ? text('本机 Codex 无需填写 API Key；也可以连接自己的国内外模型 API。', 'Local Codex needs no API key. You can also connect another model provider.')
      : text('国内与国际模型，一个研究入口。使用供应商自己的 API Key。', 'Domestic and international models in one workspace. Bring your provider API key.')}</p>
    {access?.local_codex && <LocalCodexPanel lang={lang} />}
    {access?.local_codex && <h3>{text('其他模型 API · 可选，使用 Codex 时无需填写', 'Other model APIs · optional when using Codex')}</h3>}
    {access?.commercial_mode && <p className="model-security-note">{text('客户模式：每个账户只使用自己的 API，不共享运营者的 Codex 额度或系统密钥。', 'Customer mode: each account uses its own API, without sharing the operator’s Codex quota or system key.')}</p>}
    <p className="model-security-note">{text('密钥仅暂存在服务端内存，24 小时后或服务重启失效；不写入浏览器存储、研究记录或项目配置。线上部署须使用 HTTPS，且只连接你信任的服务。', 'Keys stay in server memory for up to 24 hours or until restart, never in browser storage, research records or project config. Use HTTPS in production and only trusted providers.')}</p>
    {!user && <p className="model-security-note"><Link to="/user/login">{text('先登录', 'Sign in')}</Link>{text('后查看当前账户可用的模型连接方式。', ' to see the model connections available to your account.')}</p>}
    {!securePage && <p className="form-error" role="alert">{text('请通过 HTTPS 或本机 localhost 打开页面，再填写密钥。', 'Open this page over HTTPS or localhost before entering a key.')}</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
    {notice && <p className="form-success" role="status">{notice}</p>}
    {connection && <div className="model-connection-status">
      <Check size={17} /><div><strong>{text('已暂存', 'Saved')} · {connection.model}</strong>
        <span>{connection.base_url}</span><span>{text('失效时间', 'Expires')} · {new Date(connection.expires_at).toLocaleString(lang === 'zh' ? 'zh-CN' : 'en-US')}</span></div>
    </div>}
    <form className="user-form" onSubmit={(event) => { event.preventDefault(); void save() }}>
      <fieldset disabled={!user || !ready || busy || !securePage}>
        <label className="form-group">{text('模型供应商', 'Provider')}<select value={provider} onChange={(event) => selectProvider(event.target.value)}>
          {presets.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          <option value="custom">{text('自定义兼容接口', 'Custom compatible endpoint')}</option>
        </select></label>
        <label className="form-group">{text('接口基础地址 / Base URL', 'Base URL')}<input type="url" required value={baseUrl} maxLength={512}
          onChange={(event) => { setBaseUrl(event.target.value); setProvider('custom'); setApiKey(''); edited() }} autoComplete="off" spellCheck={false} /></label>
        <label className="form-group">{text('模型名称 / Model ID', 'Model ID')}<input required value={model} maxLength={128}
          placeholder={text('从供应商控制台复制模型名或推理接入点 ID', 'Copy the model name or deployment ID from your provider')}
          onChange={(event) => { setModel(event.target.value); edited() }} autoComplete="off" spellCheck={false} /></label>
        <label className="form-group">API Key<input type="password" required value={apiKey} maxLength={4096}
          placeholder={connection ? text('替换设置需重新填写密钥', 'Re-enter key to replace settings') : text('粘贴你自己的 API Key', 'Paste your API key')}
          onChange={(event) => { setApiKey(event.target.value); edited() }} autoComplete="new-password" spellCheck={false} /></label>
        <details className="model-advanced"><summary>{text('协议与兼容设置', 'Protocol & compatibility')}</summary>
          <label className="form-group">{text('接口协议', 'Protocol')}<select value={protocol} onChange={(event) => { setProtocol(event.target.value as ModelProtocol); setApiKey(''); edited() }}>
            <option value="openai">OpenAI Chat Completions</option><option value="anthropic">Anthropic Messages</option>
          </select></label>
          {protocol === 'openai' && <label className="form-group">{text('输出上限参数', 'Output limit parameter')}<select value={tokenParameter} onChange={(event) => { setTokenParameter(event.target.value as TokenParameter); edited() }}>
            <option value="max_tokens">max_tokens</option><option value="max_completion_tokens">max_completion_tokens</option>
          </select></label>}
          <p>{text('使用供应商默认采样参数；仅接入文本研究，未接入语音、视频或供应商原生搜索。基础地址不要包含 /chat/completions、/messages 或 /responses。', 'Uses provider sampling defaults. Text research only; no audio, video or native provider search. Do not include /chat/completions, /messages or /responses in the base URL.')}</p>
        </details>
        <button className="form-submit" type="submit">{busy ? text('处理中…', 'Working…') : text('保存并用于研究', 'Save and use for research')}</button>
      </fieldset>
    </form>
    {dirty && connection && <p className="model-security-note">{text('表单尚未保存；研究仍使用上方已暂存的配置。', 'Unsaved edits: research still uses the saved configuration shown above.')}</p>}
    <div className="model-test-area">
      <label><input type="checkbox" checked={testConsent} disabled={!connection || dirty || busy} onChange={(event) => setTestConsent(event.target.checked)} />
        {text('同意发送一次短测试（输出上限 128 token），可能产生供应商费用。', 'Allow one short test (up to 128 output tokens); provider charges may apply.')}</label>
      <div className="model-actions">
        <button type="button" disabled={!connection || dirty || busy || !testConsent} onClick={() => void test()}><FlaskConical size={15} />{text('测试连接', 'Test connection')}</button>
        <button type="button" disabled={!connection || busy} onClick={() => void disconnect()}><Unplug size={15} />{text('断开并清除密钥', 'Disconnect and clear key')}</button>
        <Link to="/chat">{text('返回金融助手', 'Back to research')}</Link>
      </div>
    </div>
    <details className="model-advanced"><summary>{text('地址限制与使用说明', 'Endpoint rules & usage notes')}</summary>
      <p>{text('允许的域名：', 'Allowed hosts: ')}{allowedHosts.join(', ') || text('等待后端加载', 'Waiting for the backend')}</p>
      <p>{text('其他 HTTPS 兼容服务须由管理员加入域名白名单。不同地区的地址与密钥应匹配；网页会员或 Coding Plan 不一定允许在此使用，请遵循供应商条款。保存不发起模型请求，测试与正式研究可能计费。', 'An administrator must allow other HTTPS endpoints. Match regional keys and URLs; chat subscriptions or coding plans may not permit this use. Saving makes no model request; testing and research may incur charges.')}</p>
    </details>
  </div></div>
}
