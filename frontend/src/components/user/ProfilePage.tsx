import { useState } from 'react'
import { User, Mail, Calendar, Edit3, Save, X } from 'lucide-react'
import { apiUpdateProfile } from '../../api/auth'
import { useUserStore } from '../../store/user'
import { translate } from '../../i18n'
import { useWorkspace } from '../../store/workspace'

export default function ProfilePage() {
  const user = useUserStore((s) => s.user)
  const updateUser = useUserStore((s) => s.updateUser)
  const clearAuth = useUserStore((s) => s.clearAuth)
  const lang = useWorkspace((s) => s.lang)
  const t = (k: string) => translate(lang, k)

  const [editing, setEditing] = useState(false)
  const [displayName, setDisplayName] = useState(user?.display_name || '')
  const [avatarUrl, setAvatarUrl] = useState(user?.avatar_url || '')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  if (!user) {
    return (
      <div className="user-page">
        <div className="user-page-card">
          <p>{t('loginRequired')}</p>
        </div>
      </div>
    )
  }

  const handleSave = async () => {
    setError('')
    setSaving(true)
    try {
      const updated = await apiUpdateProfile({
        display_name: displayName,
        avatar_url: avatarUrl || undefined,
      })
      updateUser(updated)
      setEditing(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Update failed')
    } finally {
      setSaving(false)
    }
  }

  const handleCancel = () => {
    setDisplayName(user.display_name)
    setAvatarUrl(user.avatar_url || '')
    setEditing(false)
    setError('')
  }

  const formatDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleDateString(lang === 'zh' ? 'zh-CN' : 'en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      })
    } catch {
      return iso
    }
  }

  return (
    <div className="user-page">
      <div className="user-page-card profile-card">
        <div className="profile-header">
          <div className="profile-avatar">
            {user.avatar_url ? (
              <img src={user.avatar_url} alt={user.display_name} />
            ) : (
              <User size={40} />
            )}
          </div>
          <div className="profile-header-info">
            <h2>{user.display_name || user.username}</h2>
            <span className="profile-username">@{user.username}</span>
          </div>
          {!editing && (
            <button className="edit-btn" onClick={() => setEditing(true)}>
              <Edit3 size={14} />
              {t('edit')}
            </button>
          )}
        </div>

        {editing && (
          <div className="profile-edit-form">
            <div className="form-group">
              <label>{t('displayName')}</label>
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                maxLength={128}
              />
            </div>
            <div className="form-group">
              <label>{t('avatarUrl')}</label>
              <input
                type="url"
                value={avatarUrl}
                onChange={(e) => setAvatarUrl(e.target.value)}
                placeholder={t('avatarUrlPh')}
                maxLength={512}
              />
            </div>
            {error && <div className="form-error">{error}</div>}
            <div className="form-actions">
              <button className="form-submit" onClick={handleSave} disabled={saving}>
                <Save size={14} />
                {saving ? t('saving') : t('save')}
              </button>
              <button className="form-cancel" onClick={handleCancel}>
                <X size={14} />
                {t('cancel')}
              </button>
            </div>
          </div>
        )}

        <div className="profile-info-list">
          <div className="profile-info-item">
            <Mail size={16} />
            <span className="profile-info-label">{t('email')}</span>
            <span className="profile-info-value">{user.email}</span>
          </div>
          <div className="profile-info-item">
            <Calendar size={16} />
            <span className="profile-info-label">{t('registeredAt')}</span>
            <span className="profile-info-value">{formatDate(user.created_at)}</span>
          </div>
        </div>

        <div className="profile-footer">
          <button className="logout-btn" onClick={clearAuth}>
            {t('logout')}
          </button>
        </div>
      </div>
    </div>
  )
}
