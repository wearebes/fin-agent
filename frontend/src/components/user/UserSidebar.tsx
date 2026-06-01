import { useNavigate, useLocation } from 'react-router-dom'
import { User, LogIn, UserPlus, KeyRound } from 'lucide-react'
import { translate } from '../../i18n'
import { useWorkspace } from '../../store/workspace'

const NAV_ITEMS = [
  { path: '/user/login', icon: LogIn, labelKey: 'userLogin' },
  { path: '/user/register', icon: UserPlus, labelKey: 'userRegister' },
  { path: '/user/profile', icon: User, labelKey: 'userProfile' },
  { path: '/user/password', icon: KeyRound, labelKey: 'userPassword' },
]

export default function UserSidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const lang = useWorkspace((s) => s.lang)
  const t = (k: string) => translate(lang, k)

  return (
    <aside className="user-sidebar">
      <div className="user-sidebar-header">
        <User size={20} />
        <span>{t('userCenter')}</span>
      </div>
      <nav className="user-sidebar-nav">
        {NAV_ITEMS.map((item) => {
          const active = location.pathname === item.path
          return (
            <button
              key={item.path}
              className={`user-nav-item ${active ? 'active' : ''}`}
              onClick={() => navigate(item.path)}
            >
              <item.icon size={16} />
              <span>{t(item.labelKey)}</span>
            </button>
          )
        })}
      </nav>
    </aside>
  )
}
