import { useState, type FormEvent } from 'react'
import { KeyRound, LockKeyhole, Save } from 'lucide-react'
import { saveLocalSetup } from '../api/local'

export default function LocalSetupPage({ onComplete }: { onComplete: () => void }) {
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState('gpt-4.1-mini')
  const [baseUrl, setBaseUrl] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setSaving(true)
    try {
      await saveLocalSetup({ api_key: apiKey, model, base_url: baseUrl || undefined })
      onComplete()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '保存失败，请检查后重试。')
    } finally {
      setSaving(false)
    }
  }

  return (
    <main className="local-setup">
      <section className="local-setup-card">
        <div className="local-setup-icon"><KeyRound size={25} /></div>
        <span>FINAGENT / 本地个人版</span>
        <h1>接入你自己的 API</h1>
        <p>密钥只保存在这台电脑的本地配置中，不会上传到 FinAgent。</p>
        <form onSubmit={submit}>
          <label>OpenAI API Key<input type="password" autoComplete="off" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="sk-..." required /></label>
          <label>模型<input value={model} onChange={(event) => setModel(event.target.value)} required /></label>
          <label>兼容接口地址（可选）<input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://api.openai.com/v1" /></label>
          {error && <p className="local-setup-error">{error}</p>}
          <button type="submit" disabled={saving}><Save size={16} />{saving ? '正在保存…' : '保存并开始使用'}</button>
        </form>
        <small><LockKeyhole size={13} />会话与本地账号也会保存到这台电脑的 SQLite 数据库。</small>
      </section>
    </main>
  )
}
