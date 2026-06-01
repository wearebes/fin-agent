import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { UserPlus } from 'lucide-react'
import { apiRegister } from '../../api/auth'
import { useUserStore } from '../../store/user'
import { translate } from '../../i18n'
import { useWorkspace } from '../../store/workspace'

export default function RegisterPage() {
  const navigate = useNavigate()
  const setAuth = useUserStore((s) => s.setAuth)
  const lang = useWorkspace((s) => s.lang)
  const t = (k: string) => translate(lang, k)

  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (password !== confirmPassword) {
      setError(t('passwordMismatch'))
      return
    }
    setLoading(true)
    try {
      const res = await apiRegister({
        username,
        email,
        password,
        display_name: displayName || username,
      })
      setAuth(res.access_token, res.user)
      navigate('/user/profile')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="user-page">
      <div className="user-page-card">
        <div className="user-page-icon">
          <UserPlus size={28} />
        </div>
        <h2>{t('userRegister')}</h2>
        <p className="user-page-subtitle">{t('registerSubtitle')}</p>
        <form onSubmit={handleSubmit} className="user-form">
          <div className="form-group">
            <label>{t('username')}</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={t('usernamePh')}
              required
              minLength={3}
              maxLength={64}
            />
          </div>
          <div className="form-group">
            <label>{t('email')}</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t('emailPh')}
              required
            />
          </div>
          <div className="form-group">
            <label>{t('displayName')}</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder={t('displayNamePh')}
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
          <div className="form-group">
            <label>{t('confirmPassword')}</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder={t('confirmPasswordPh')}
              required
              minLength={6}
            />
          </div>
          {error && <div className="form-error">{error}</div>}
          <button type="submit" className="form-submit" disabled={loading}>
            {loading ? t('registering') : t('userRegister')}
          </button>
        </form>
        <p className="user-page-switch">
          {t('hasAccount')}{' '}
          <button className="link-btn" onClick={() => navigate('/user/login')}>
            {t('userLogin')}
          </button>
        </p>
      </div>
    </div>
  )
}
