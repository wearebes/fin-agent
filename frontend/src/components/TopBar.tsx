import { useNavigate } from 'react-router-dom'
import { translate } from '../i18n'
import { useWorkspace } from '../store/workspace'

export default function TopBar({ isQuant }: { isQuant: boolean }) {
  const navigate = useNavigate()
  const lang = useWorkspace((s) => s.lang)
  const setLang = useWorkspace((s) => s.setLang)
  const t = (k: string) => translate(lang, k)

  return (
    <nav className={`topbar ${isQuant ? 'dark' : 'light'}`}>
      <div className="topbar-inner">
        <button className="brand" onClick={() => navigate('/chat')}>
          Fin<span>Agent</span>
        </button>
        <div className="tabs">
          <button
            className={`tab ${!isQuant ? 'active' : ''}`}
            onClick={() => navigate('/chat')}
          >
            {t('navAgent')}
          </button>
          <button
            className={`tab ${isQuant ? 'active' : ''}`}
            onClick={() => navigate('/quant')}
          >
            {t('navQuant')}
          </button>
        </div>
        <div className="lang-toggle">
          <button className={lang === 'zh' ? 'active' : ''} onClick={() => setLang('zh')}>
            中文
          </button>
          <button className={lang === 'en' ? 'active' : ''} onClick={() => setLang('en')}>
            EN
          </button>
        </div>
      </div>
    </nav>
  )
}
