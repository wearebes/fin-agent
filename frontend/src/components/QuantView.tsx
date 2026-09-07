import { ChevronDown, FlaskConical } from 'lucide-react'
import { translate } from '../i18n'
import { useWorkspace } from '../store/workspace'
import QuantWorkbench from './QuantForensics'
import Starfield from './Starfield'

export default function QuantView() {
  const lang = useWorkspace((s) => s.lang)
  const t = (k: string) => translate(lang, k)

  return (
    <div className="quant-page">
      <Starfield />
      <div className="quant-hero">
        <h1>
          <span>{t('quantTitle')}</span>
        </h1>
        <p>{t('quantDesc')}</p>
      </div>
      <div className="quant-workspace">
        <details className="quant-workbench">
          <summary>
            <span className="quant-workbench-icon"><FlaskConical size={22} /></span>
            <strong className="quant-workbench-title">{t('quantWorkspaceTitle')}</strong>
            <span className="quant-workbench-toggle">
              <span className="quant-workbench-expand">{t('quantWorkspaceExpand')}</span>
              <span className="quant-workbench-collapse">{t('quantWorkspaceCollapse')}</span>
              <ChevronDown size={18} />
            </span>
          </summary>
          <QuantWorkbench />
        </details>
      </div>
      <div className="quant-footer">
        <span>{t('footer')}</span>
      </div>
    </div>
  )
}
