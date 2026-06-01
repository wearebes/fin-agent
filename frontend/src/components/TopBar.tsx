import { useNavigate } from 'react-router-dom'
import { User } from 'lucide-react'
import { translate } from '../i18n'
import { useWorkspace } from '../store/workspace'
import { useUserStore } from '../store/user'

export default function TopBar({ isQuant, isUser }: { isQuant: boolean; isUser: boolean }) {
  const navigate = useNavigate()
  const lang = useWorkspace((s) => s.lang)
  const setLang = useWorkspace((s) => s.setLang)
  const currentUser = useUserStore((s) => s.user)
  const t = (k: string) => translate(lang, k)

  return (
    <nav className={`topbar ${isQuant ? 'dark' : 'light'}`}>
      <div className="topbar-inner">
        <button className="brand" onClick={() => navigate('/chat')}>
          Fin<span>Agent</span>
        </button>
        <div className="tabs">
          <button
            className={`tab ${!isQuant && !isUser ? 'active' : ''}`}
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
        <div className="topbar-right">
          <div className="lang-toggle">
            <button className={lang === 'zh' ? 'active' : ''} onClick={() => setLang('zh')}>
              中文
            </button>
            <button className={lang === 'en' ? 'active' : ''} onClick={() => setLang('en')}>
              EN
            </button>
          </div>
          <button
            className={`user-btn ${isUser ? 'active' : ''}`}
            onClick={() => navigate(currentUser ? '/user/profile' : '/user/login')}
            title={currentUser ? currentUser.display_name || currentUser.username : t('navUser')}
          >
            {currentUser?.avatar_url ? (
              <img src={currentUser.avatar_url} alt="" className="user-avatar-sm" />
            ) : (
              <User size={18} />
            )}
            {currentUser && <span className="user-name-sm">{currentUser.display_name || currentUser.username}</span>}
          </button>
        </div>
      </div>
    </nav>
  )
}
