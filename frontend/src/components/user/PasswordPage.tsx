import { useState } from 'react'
import { KeyRound } from 'lucide-react'
import { apiChangePassword } from '../../api/auth'
import { useUserStore } from '../../store/user'
import { translate } from '../../i18n'
import { useWorkspace } from '../../store/workspace'

export default function PasswordPage() {
  const user = useUserStore((s) => s.user)
  const lang = useWorkspace((s) => s.lang)
  const t = (k: string) => translate(lang, k)

  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)

  if (!user) {
    return (
      <div className="user-page">
        <div className="user-page-card">
          <p>{t('loginRequired')}</p>
        </div>
      </div>
    )
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccess('')
    if (newPassword !== confirmPassword) {
      setError(t('passwordMismatch'))
      return
    }
    setLoading(true)
    try {
      await apiChangePassword({ old_password: oldPassword, new_password: newPassword })
      setSuccess(t('passwordChanged'))
      setOldPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="user-page">
      <div className="user-page-card">
        <div className="user-page-icon">
          <KeyRound size={28} />
        </div>
        <h2>{t('changePassword')}</h2>
        <form onSubmit={handleSubmit} className="user-form">
          <div className="form-group">
            <label>{t('oldPassword')}</label>
            <input
              type="password"
              value={oldPassword}
              onChange={(e) => setOldPassword(e.target.value)}
              placeholder={t('oldPasswordPh')}
              required
            />
          </div>
          <div className="form-group">
            <label>{t('newPassword')}</label>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder={t('newPasswordPh')}
              required
              minLength={6}
            />
          </div>
          <div className="form-group">
            <label>{t('confirmNewPassword')}</label>
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
          {success && <div className="form-success">{success}</div>}
          <button type="submit" className="form-submit" disabled={loading}>
            {loading ? t('saving') : t('changePassword')}
          </button>
        </form>
      </div>
    </div>
  )
}
