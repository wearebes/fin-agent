import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Puzzle, Lock, Trash2, Upload, RefreshCw, Link2 } from 'lucide-react'
import {
  deleteSkill,
  installSkillFromUrl,
  listSkillsWithSource,
  reloadSkills,
  uploadSkill,
  type SkillDetail,
} from '../../api/skills'
import { translate } from '../../i18n'
import { useWorkspace } from '../../store/workspace'

const SKILLS_QUERY_KEY = ['skills-detail'] as const

type Toast = { kind: 'success' | 'error'; msg: string }

export default function SkillsPage() {
  const lang = useWorkspace((s) => s.lang)
  const t = (k: string) => translate(lang, k)
  const qc = useQueryClient()

  const [url, setUrl] = useState('')
  const [confirmId, setConfirmId] = useState<string | null>(null)
  const [toast, setToast] = useState<Toast | null>(null)
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const showToast = (kind: Toast['kind'], msg: string) => {
    setToast({ kind, msg })
    if (toastTimer.current) clearTimeout(toastTimer.current)
    toastTimer.current = setTimeout(() => setToast(null), 3000)
  }

  const {
    data: skills = [],
    isLoading,
    error,
  } = useQuery<SkillDetail[]>({
    queryKey: SKILLS_QUERY_KEY,
    queryFn: listSkillsWithSource,
  })

  const refresh = () => qc.invalidateQueries({ queryKey: SKILLS_QUERY_KEY })

  const installMut = useMutation({
    mutationFn: (target: string) => installSkillFromUrl(target),
    onSuccess: (r) => {
      setUrl('')
      showToast('success', `${t('skillsInstallOk')}${r.name ?? ''}`)
      refresh()
    },
    onError: (e: Error) => showToast('error', e.message),
  })

  const uploadMut = useMutation({
    mutationFn: (file: File) => uploadSkill(file),
    onSuccess: (r) => {
      showToast('success', `${t('skillsUploadOk')}${r.name ?? ''}`)
      refresh()
    },
    onError: (e: Error) => showToast('error', e.message),
  })

  const deleteMut = useMutation({
    mutationFn: (name: string) => deleteSkill(name),
    onSuccess: (r) => {
      showToast('success', `${t('skillsDeleteOk')}${r.name ?? ''}`)
      refresh()
    },
    onError: (e: Error) => showToast('error', e.message),
  })

  const reloadMut = useMutation({
    mutationFn: () => reloadSkills(),
    onSuccess: (r) => {
      showToast('success', `${t('skillsReloaded')} (${r.total_skills})`)
      refresh()
    },
    onError: (e: Error) => showToast('error', e.message),
  })

  const onPickFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) uploadMut.mutate(file)
    e.target.value = '' // reset so re-picking the same file fires onChange again
  }

  const onDeleteClick = (name: string) => {
    if (confirmId === name) {
      deleteMut.mutate(name)
      setConfirmId(null)
    } else {
      setConfirmId(name)
    }
  }

  return (
    <div className="user-page">
      <div className="user-page-card skills-card">
        <div className="user-page-icon">
          <Puzzle size={24} />
        </div>
        <h2>{t('skillsTitle')}</h2>
        <p className="user-page-subtitle">{t('skillsSubtitle')}</p>

        {toast && <div className={`toast toast-${toast.kind}`}>{toast.msg}</div>}

        {/* Installed list */}
        <div className="skills-section">
          <h3>
            {t('skillsInstalled')}
            {skills.length > 0 && <span className="skills-count">{skills.length}</span>}
          </h3>
          {isLoading && <p className="skills-hint">{t('skillsLoading')}</p>}
          {error && <div className="form-error">{(error as Error).message}</div>}
          {!isLoading && !error && skills.length === 0 && (
            <p className="skills-hint">{t('skillsEmpty')}</p>
          )}
          <div className="skill-list">
            {skills.map((s) => (
              <div className="skill-row" key={s.name}>
                <div className="skill-row-info">
                  <div className="skill-row-head">
                    <span className="skill-name">{s.name}</span>
                    <span className="skill-trigger">{s.trigger}</span>
                    <span className={`skill-source-badge ${s.source}`}>
                      {s.source === 'builtin' && <Lock size={11} />}
                      {s.source === 'builtin' ? t('skillsBuiltin') : t('skillsExternal')}
                    </span>
                  </div>
                  {s.description && <span className="skill-desc">{s.description}</span>}
                </div>
                {s.source === 'external' ? (
                  <button
                    className={`skill-delete-btn ${confirmId === s.name ? 'confirming' : ''}`}
                    onClick={() => onDeleteClick(s.name)}
                    disabled={deleteMut.isPending}
                    title={t('skillsDelete')}
                  >
                    <Trash2 size={14} />
                    {confirmId === s.name ? t('confirmDelete') : t('skillsDelete')}
                  </button>
                ) : (
                  <span className="skill-locked" title={t('skillsBuiltinLock')}>
                    <Lock size={14} />
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Install from URL */}
        <div className="skills-section">
          <h3>{t('skillsInstallUrl')}</h3>
          <div className="skills-install-row">
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder={t('skillsUrlPh')}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && url.trim()) installMut.mutate(url.trim())
              }}
            />
            <button
              className="form-submit"
              disabled={!url.trim() || installMut.isPending}
              onClick={() => installMut.mutate(url.trim())}
            >
              <Link2 size={14} />
              {installMut.isPending ? t('skillsInstalling') : t('skillsInstall')}
            </button>
          </div>
        </div>

        {/* Upload + reload */}
        <div className="skills-section">
          <h3>{t('skillsManage')}</h3>
          <div className="skills-actions">
            <input
              ref={fileRef}
              type="file"
              accept=".md,text/markdown"
              style={{ display: 'none' }}
              onChange={onPickFile}
            />
            <button
              className="form-cancel"
              onClick={() => fileRef.current?.click()}
              disabled={uploadMut.isPending}
            >
              <Upload size={14} />
              {uploadMut.isPending ? t('skillsUploading') : t('skillsUpload')}
            </button>
            <button
              className="form-cancel"
              onClick={() => reloadMut.mutate()}
              disabled={reloadMut.isPending}
            >
              <RefreshCw size={14} />
              {reloadMut.isPending ? t('skillsReloading') : t('skillsReload')}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
