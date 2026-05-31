import { translate } from '../i18n'
import { useWorkspace } from '../store/workspace'
import Starfield from './Starfield'

const features = [
  { icon: '🔄', nameKey: 'qBacktest', descKey: 'qBacktestD' },
  { icon: '🔧', nameKey: 'qModel', descKey: 'qModelD' },
  { icon: '📋', nameKey: 'qPaper', descKey: 'qPaperD' },
  { icon: '⚡', nameKey: 'qLive', descKey: 'qLiveD' },
]

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
      <div className="quant-content">
        <div className="quant-grid">
          {features.map((f) => (
            <div className="q-card" key={f.nameKey}>
              <div className="q-icon">{f.icon}</div>
              <div className="q-name">{t(f.nameKey)}</div>
              <div className="q-desc">{t(f.descKey)}</div>
              <div className="q-badge">
                <span className="q-badge-dot" />
                {t('soon')}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="quant-footer">
        <span>{t('footer')}</span>
      </div>
    </div>
  )
}
