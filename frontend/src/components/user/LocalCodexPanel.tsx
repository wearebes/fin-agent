import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCodexStatus, testCodexConnection } from '../../api/models'
import { useUserStore } from '../../store/user'

export default function LocalCodexPanel({ lang }: { lang: 'zh' | 'en' }) {
  const navigate = useNavigate()
  const setSource = useUserStore((s) => s.setModelSource)
  const [busy, setBusy] = useState(false)
  const [consent, setConsent] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const text = (zh: string, en: string) => lang === 'zh' ? zh : en

  async function connect(test: boolean) {
    setBusy(true); setError(''); setNotice(''); setConsent(false)
    try {
      if (test) {
        const result = await testCodexConnection()
        setNotice(`${text('真实返回', 'Live response')}: ${result.text} · ${result.model} · ${text('输入 / 输出 token', 'Input / output tokens')}: ${result.input_tokens ?? '—'} / ${result.output_tokens ?? '—'}`)
      } else {
        await getCodexStatus()
        setSource('codex')
        navigate('/chat')
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally { setBusy(false) }
  }

  return <section className="model-local-panel">
    <h3>{text('本机 Codex · 仅本人使用', 'Local Codex · owner only')}</h3>
    <p>{text('通过官方本机接口使用你的 ChatGPT / Codex 额度，不读取或复制登录密钥。客户使用下方独立 API；商业部署关闭此入口。', 'Uses your ChatGPT / Codex quota through the official local interface without copying credentials. Customers use separate API connections below; this entry is disabled in commercial mode.')}</p>
    <button type="button" disabled={busy} onClick={() => void connect(false)}>{text('使用本机 Codex（无需 API Key）', 'Use local Codex (no API key needed)')}</button>
    <label className="model-test-consent"><input type="checkbox" checked={consent} disabled={busy} onChange={(event) => setConsent(event.target.checked)} />
      {text('允许一轮真实短测试，消耗 Codex 额度。这里没有 API 的 128 token 硬上限，超时会停止本地进程。', 'Allow one live short test using Codex quota. The API 128-token hard cap does not apply; timeouts stop the local process.')}</label>
    <button type="button" disabled={busy || !consent} onClick={() => void connect(true)}>{busy ? text('处理中…', 'Working…') : text('真实测试 Codex', 'Test Codex live')}</button>
    <p>{text('完整研究会按原流程调用多次模型，仍使用原金融数据接口。失败不会切换到其他 API。', 'Full research uses multiple model calls and the existing financial data sources. Failures never switch to another API.')}</p>
    {notice && <p role="status" className="form-success">{notice}</p>}
    {error && <p role="alert" className="form-error">{error}</p>}
  </section>
}
