import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowUp, ListChecks, Workflow, X } from 'lucide-react'
import { listSkills } from '../api/skills'
import type { Skill } from '../api/skills'
import { translate } from '../i18n'
import type { Lang, ResearchMode } from '../types'
import { useWorkspace } from '../store/workspace'

interface SlashToken {
  start: number
  end: number
  query: string
}

/**
 * Locates the '/'-prefixed token the caret currently sits inside, e.g. typing
 * "请分析 /val" with the caret at the end yields `{ start: 4, end: 9, query:
 * 'val' }`. Mirrors Slack/Notion-style slash triggers: '/' must start a
 * "word" (preceded by start-of-text or whitespace) and the caret must be
 * strictly past it; the query itself may not contain whitespace or another
 * '/'. Returns `null` when the caret isn't inside such a token.
 */
function findSlashToken(text: string, caret: number): SlashToken | null {
  let start = caret
  while (start > 0 && !/\s/.test(text[start - 1])) start--
  if (start === caret || text[start] !== '/') return null
  const query = text.slice(start + 1, caret)
  if (query.includes('/')) return null
  return { start, end: caret, query }
}

function matchesSkill(skill: Skill, query: string): boolean {
  if (!query) return true
  const q = query.toLowerCase()
  return (
    skill.name.toLowerCase().includes(q) ||
    skill.trigger.toLowerCase().includes(q) ||
    skill.aliases.some((alias) => alias.toLowerCase().includes(q))
  )
}

export default function Composer({
  lang,
  disabled,
  onSubmit,
  draft,
  onChange,
  useHistory,
  onHistoryChange,
  hasHistory,
}: {
  lang: Lang
  disabled: boolean
  onSubmit: (question: string, ticker: string | null, selectedSkill: string | null, mode: ResearchMode) => void
  draft: { question: string; ticker: string }
  onChange: (draft: { question: string; ticker: string }) => void
  useHistory: boolean
  onHistoryChange: (enabled: boolean) => void
  hasHistory: boolean
}) {
  const { question, ticker } = draft
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [pickerQuery, setPickerQuery] = useState('')
  const [pickerIndex, setPickerIndex] = useState(0)
  const t = (k: string) => translate(lang, k)
  const showThinking = useWorkspace((s) => s.showThinking)
  const setShowThinking = useWorkspace((s) => s.setShowThinking)
  const planMode = useWorkspace((s) => s.planMode)
  const setPlanMode = useWorkspace((s) => s.setPlanMode)

  const textareaRef = useRef<HTMLTextAreaElement>(null)
  // Caret offset to restore after a skill pick trims the '/token' out of the
  // question — applied from a layout effect once the DOM reflects the new
  // (shorter) value; setting it synchronously would clamp against the stale one.
  const pendingCaretRef = useRef<number | null>(null)

  // Anonymous catalog listing (GET /v1/skills) — purely for picker
  // filtering/display. The catalog is small and effectively static for the
  // lifetime of a session, so a long staleTime avoids redundant refetches.
  const { data: skills = [] } = useQuery({
    queryKey: ['skills'],
    queryFn: listSkills,
    staleTime: 5 * 60 * 1000,
  })

  const filteredSkills = useMemo(
    () => skills.filter((skill) => matchesSkill(skill, pickerQuery)),
    [skills, pickerQuery],
  )

  // Keep the highlighted row in range as filtering narrows the list.
  useEffect(() => {
    setPickerIndex((i) => Math.min(i, Math.max(filteredSkills.length - 1, 0)))
  }, [filteredSkills.length])

  useLayoutEffect(() => {
    const pos = pendingCaretRef.current
    if (pos === null) return
    pendingCaretRef.current = null
    const el = textareaRef.current
    if (el) {
      el.focus()
      el.setSelectionRange(pos, pos)
    }
  }, [question])

  const closePicker = () => {
    setPickerOpen(false)
    setPickerQuery('')
  }

  // Removes the active '/token' (if the caret is still inside one — it may
  // have moved between the keystroke that opened the picker and the click/key
  // that resolved it) and records the chosen skill as a chip rather than text:
  // `selected_skill` travels to the backend as its own field, never parsed
  // out of `question` server-side, so leaving "/valuation" in the message
  // would just be confusing duplication.
  const selectSkill = (skill: Skill) => {
    const el = textareaRef.current
    const caret = el?.selectionStart ?? question.length
    const token = findSlashToken(question, caret)
    if (token) {
      const before = question.slice(0, token.start)
      let after = question.slice(token.end)
      if (before.endsWith(' ') && after.startsWith(' ')) after = after.slice(1)
      pendingCaretRef.current = token.start
      onChange({ ...draft, question: before + after })
    }
    setSelectedSkill(skill)
    closePicker()
  }

  const clearSkill = () => {
    setSelectedSkill(null)
    textareaRef.current?.focus()
  }

  const submit = () => {
    const q = question.trim()
    if (!q || disabled) return
    onSubmit(q, ticker.trim() || null, selectedSkill?.name ?? null, planMode ? 'plan' : 'auto')
    onChange({ question: '', ticker: '' })
    setSelectedSkill(null)
    closePicker()
  }

  const onChangeQuestion = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value
    onChange({ ...draft, question: value })
    const caret = e.target.selectionStart ?? value.length
    const token = findSlashToken(value, caret)
    if (token) {
      setPickerQuery(token.query)
      setPickerOpen(true)
      setPickerIndex(0)
    } else if (pickerOpen) {
      closePicker()
    }
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (pickerOpen) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setPickerIndex((i) => (filteredSkills.length === 0 ? 0 : (i + 1) % filteredSkills.length))
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setPickerIndex((i) =>
          filteredSkills.length === 0
            ? 0
            : (i - 1 + filteredSkills.length) % filteredSkills.length,
        )
        return
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        const picked = filteredSkills[pickerIndex]
        if (picked) {
          e.preventDefault()
          selectSkill(picked)
        }
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        closePicker()
        return
      }
    }
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && !e.nativeEvent.isComposing) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="composer">
      <div className="composer-card">
        {pickerOpen && (
          <div className="skill-picker">
            {filteredSkills.length === 0 ? (
              <div className="skill-picker-empty">{t('skillPickerEmpty')}</div>
            ) : (
              <ul className="skill-picker-list">
                {filteredSkills.map((skill, i) => (
                  <li
                    key={skill.name}
                    className={`skill-picker-item${i === pickerIndex ? ' active' : ''}`}
                    onMouseDown={(e) => {
                      // Keep focus (and the live selection) on the textarea —
                      // a default mousedown would blur it first and strand
                      // `selectSkill` without a caret to resolve the token from.
                      e.preventDefault()
                      selectSkill(skill)
                    }}
                    onMouseEnter={() => setPickerIndex(i)}
                  >
                    <span className="skill-picker-slash">{skill.trigger}</span>
                    <span className="skill-picker-desc">{skill.description}</span>
                  </li>
                ))}
              </ul>
            )}
            <div className="skill-picker-hint">{t('skillPickerHint')}</div>
          </div>
        )}

        {selectedSkill && (
          <div className="composer-skill-chip">
            <span className="composer-skill-slash">{selectedSkill.trigger}</span>
            <span className="composer-skill-desc">{selectedSkill.description}</span>
            <button
              type="button"
              className="composer-skill-clear"
              onClick={clearSkill}
              title={t('removeSkill')}
              aria-label={t('removeSkill')}
            >
              <X size={12} />
            </button>
          </div>
        )}

        <textarea
          ref={textareaRef}
          className="composer-q"
          placeholder={t('phQ')}
          aria-label={t('questionLabel')}
          value={question}
          onChange={onChangeQuestion}
          onKeyDown={onKeyDown}
          onBlur={closePicker}
          disabled={disabled}
          rows={3}
        />
        <div className="composer-row">
          <input
            className="composer-ticker"
            type="text"
            placeholder={t('phT')}
            aria-label={t('tickerLabel')}
            value={ticker}
            onChange={(e) => onChange({ ...draft, ticker: e.target.value })}
            disabled={disabled}
          />
          <span className="composer-hint">{t('composerHint')}</span>

          <button
            type="button"
            className={`thinking-toggle${showThinking ? ' active' : ''}`}
            onClick={() => setShowThinking(!showThinking)}
            title={showThinking ? t('processOn') : t('processOff')}
            aria-pressed={showThinking}
          >
            <Workflow size={13} />
            <span className="thinking-toggle-label">{t('researchProcess')}</span>
          </button>

          <button
            type="button"
            className={`thinking-toggle${planMode ? ' active' : ''}`}
            onClick={() => setPlanMode(!planMode)}
            title={planMode ? t('planModeOn') : t('planModeOff')}
            aria-pressed={planMode}
          >
            <ListChecks size={13} />
            <span className="thinking-toggle-label">{t('planMode')}</span>
          </button>

          <button
            className="send-btn"
            onClick={submit}
            disabled={disabled || !question.trim()}
          >
            {disabled ? <span className="spinner" /> : <ArrowUp size={15} />}
            <span>{disabled ? t('sending') : t('send')}</span>
          </button>
        </div>
        {hasHistory && (
          <label className="context-option">
            <input type="checkbox" checked={useHistory} disabled={disabled}
              onChange={(event) => onHistoryChange(event.target.checked)} />
            {t('useHistory')}
          </label>
        )}
      </div>
      <p className="composer-note">{t('researchNotice')}</p>
    </div>
  )
}
