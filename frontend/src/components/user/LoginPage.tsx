import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { LogIn } from 'lucide-react'
import { apiLogin } from '../../api/auth'
import { useUserStore } from '../../store/user'
import { translate } from '../../i18n'
import { useWorkspace } from '../../store/workspace'

export default function LoginPage() {
  const navigate = useNavigate()
  const setAuth = useUserStore((s) => s.setAuth)
  const lang = useWorkspace((s) => s.lang)
  const t = (k: string) => translate(lang, k)

  const [loginName, setLoginName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await apiLogin({ login_name: loginName, password })
      setAuth(res.access_token, res.user)
      navigate('/user/profile')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="user-page">
      <div className="user-page-card">
        <div className="user-page-icon">
          <LogIn size={28} />
        </div>
        <h2>{t('userLogin')}</h2>
        <p className="user-page-subtitle">{t('loginSubtitle')}</p>
        <form onSubmit={handleSubmit} className="user-form">
          <div className="form-group">
            <label>{t('usernameOrEmail')}</label>
            <input
              type="text"
              value={loginName}
              onChange={(e) => setLoginName(e.target.value)}
              placeholder={t('usernameOrEmailPh')}
              required
            />
          </div>
          <div className="form-group">
            <label>{t('password')}</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t('passwordPh')}
              required
              minLength={6}
            />
          </div>
          {error && <div className="form-error">{error}</div>}
          <button type="submit" className="form-submit" disabled={loading}>
            {loading ? t('loggingIn') : t('userLogin')}
          </button>
        </form>
        <p className="user-page-switch">
          {t('noAccount')}{' '}
          <button className="link-btn" onClick={() => navigate('/user/register')}>
            {t('userRegister')}
          </button>
        </p>
      </div>
    </div>
  )
}
