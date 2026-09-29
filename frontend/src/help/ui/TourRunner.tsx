/**
 * "תראו לי" — מריץ הדרכה על המסך האמיתי (HELP_CENTER_PLAN.md §9).
 *
 * מה הוא עושה: עובר למסך הנכון, מוצא את היעד הגלוי (``data-help``), מסמן אותו
 * בטבעת זהב, כותב שורה אחת בכרטיס קטן לידו — ו**מחכה שהמשתמש יפעל בעצמו**.
 * ממשיך לצעד הבא לפי מה שקרה באמת (לחיצה, חלון שנפתח, שדה שמולא, או אישור
 * מהשרת). "סיימנו" רק כשהשרת אישר את הפעולה.
 *
 * מה הוא **לא** עושה, אף פעם: לא לוחץ, לא ממלא, לא שולח ולא שומר.
 * יעד שלא נמצא (או לא גלוי) תוך 4 שניות → עוצרים בהודעה כנה, בלי לנחש.
 */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { strings } from '../../strings/he'
import { onApiEvent } from '../errorBus'
import { activeScopes, subscribeScopes } from '../scopes'
import { holds } from '../engine/conditions'
import { renderText } from '../engine/text'
import type { TextContext } from '../engine/text'
import { errorMatches } from '../engine/topics'
import type { Facts } from '../facts'
import type { FlowStep, GuidedFlow, Signal } from '../types'
import { MOCK_NOTICE } from '../kb/shared'
import {
  FIND_TIMEOUT_MS, HIGHLIGHT_CLASS, findVisibleTarget, isTextField, isVisible, prefersReducedMotion,
} from './tour'

type Phase =
  | { kind: 'running'; index: number }
  | { kind: 'done' }
  | { kind: 'notfound' }
  | { kind: 'error'; tree: string }

interface Props {
  flow: GuidedFlow
  /** העובדות העדכניות (נקרא מחדש בכל צעד — למשל שלב באשף שהשתנה). */
  facts: () => Facts
  text: TextContext
  mockMode: boolean
  /** מעבר למסך שבו ההדרכה מתחילה (עם סינון, אם צריך). */
  onStart: (flow: GuidedFlow) => void
  onExit: (result: 'completed' | 'abandoned' | 'failed') => void
  onOpenTree: (treeId: string) => void
}

/** האם האות של צעד כבר מתקיים כשמגיעים אליו — ואז מדלגים עליו. */
function alreadySatisfied(sig: Signal): boolean {
  if (sig.kind === 'scope') return activeScopes().includes(sig.scope)
  if (sig.kind === 'visible') return findVisibleTarget(sig.target) !== null
  return false
}

function nextIndex(flow: GuidedFlow, from: number, facts: Facts): number {
  for (let i = from; i < flow.steps.length; i++) {
    const step = flow.steps[i]
    if (!holds(step.when, facts)) continue
    if (alreadySatisfied(step.advanceOn)) continue
    return i
  }
  return -1
}

export default function TourRunner({ flow, facts, text, mockMode, onStart, onExit, onOpenTree }: Props) {
  const t = strings.help
  const [phase, setPhase] = useState<Phase | null>(null)
  const [target, setTarget] = useState<HTMLElement | null>(null)
  const [pos, setPos] = useState<CSSProperties>({})
  const cardRef = useRef<HTMLDivElement | null>(null)
  const phaseRef = useRef<Phase | null>(null)
  phaseRef.current = phase

  const advanceFrom = useCallback(
    (from: number) => {
      const i = nextIndex(flow, from, facts())
      setTarget(null)
      setPhase(i < 0 ? { kind: 'notfound' } : { kind: 'running', index: i })
    },
    [flow, facts],
  )

  // התחלה: מעבר למסך, ואז (אחרי שהמסך עלה) הצעד הראשון שרלוונטי.
  useEffect(() => {
    onStart(flow)
    const id = window.setTimeout(() => advanceFrom(0), 350)
    return () => window.clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flow.id])

  // הצלחה / שגיאה — לפי מה שהשרת החזיר, לא לפי לחיצה.
  useEffect(() => {
    return onApiEvent((e) => {
      const p = phaseRef.current
      if (!p || p.kind !== 'running') return
      const s = flow.success
      if (e.ok && e.method === s.method && e.path === s.path) {
        setTarget(null)
        setPhase({ kind: 'done' })
        return
      }
      if (!e.ok) {
        const hit = (flow.onError ?? []).find((x) => errorMatches(x.match, e))
        if (hit) {
          setTarget(null)
          setPhase({ kind: 'error', tree: hit.tree })
        }
      }
    })
  }, [flow])

  const step: FlowStep | null = phase?.kind === 'running' ? flow.steps[phase.index] : null

  // איתור היעד של הצעד הנוכחי — ומעקב שהוא עדיין שם.
  useEffect(() => {
    if (!step || phase?.kind !== 'running') return
    const index = phase.index
    let lostSince: number | null = Date.now()
    let current: HTMLElement | null = null
    const tick = () => {
      // אות "גלוי"/"חלון נפתח" שהתקיים → הצעד הבא.
      const sig = step.advanceOn
      if ((sig.kind === 'visible' || sig.kind === 'scope') && alreadySatisfied(sig)) {
        advanceFrom(index + 1)
        return
      }
      const found = findVisibleTarget(step.target)
      if (found) {
        lostSince = null
        if (found !== current) {
          current = found
          setTarget(found)
        }
      } else {
        if (lostSince === null) lostSince = Date.now()
        if (current) {
          current = null
          setTarget(null)
        }
        if (Date.now() - lostSince > FIND_TIMEOUT_MS) {
          setPhase({ kind: 'notfound' })
          return
        }
      }
    }
    tick()
    const iv = window.setInterval(tick, 200)
    const unsub = subscribeScopes(tick)
    return () => {
      window.clearInterval(iv)
      unsub()
    }
  }, [step, phase, advanceFrom])

  // סימון היעד + המתנה לפעולה של המשתמש על היעד עצמו.
  useEffect(() => {
    if (!target || !step || phase?.kind !== 'running') return
    const index = phase.index
    target.classList.add(HIGHLIGHT_CLASS)
    target.scrollIntoView({ block: 'center', behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
    if (isTextField(target)) target.focus({ preventScroll: true })
    const sig = step.advanceOn
    const cleanups: (() => void)[] = []
    if (sig.kind === 'click') {
      // אחרי שהאפליקציה טיפלה בלחיצה — לא במקומה.
      const h = () => window.setTimeout(() => advanceFrom(index + 1), 0)
      target.addEventListener('click', h)
      cleanups.push(() => target.removeEventListener('click', h))
    }
    if (sig.kind === 'filled') {
      const h = () => {
        const v = (target as HTMLInputElement).value ?? ''
        if (v.trim()) advanceFrom(index + 1)
      }
      target.addEventListener('change', h)
      target.addEventListener('blur', h)
      cleanups.push(() => {
        target.removeEventListener('change', h)
        target.removeEventListener('blur', h)
      })
    }
    return () => {
      target.classList.remove(HIGHLIGHT_CLASS)
      for (const c of cleanups) c()
    }
  }, [target, step, phase, advanceFrom])

  // מיקום הכרטיס ליד היעד (דסקטופ) / למעלה או למטה (טלפון).
  useLayoutEffect(() => {
    let raf = 0
    let last = ''
    const apply = (next: CSSProperties) => {
      // עדכון רק כשהמיקום באמת זז — לא רינדור בכל פריים.
      const key = JSON.stringify(next)
      if (key !== last) {
        last = key
        setPos(next)
      }
    }
    const place = () => {
      const card = cardRef.current
      const narrow = window.matchMedia('(max-width: 820px)').matches
      if (!target || !isVisible(target) || !card) {
        apply(narrow ? { insetInline: 12, top: 76 } : { left: 24, bottom: 24 })
      } else {
        const r = target.getBoundingClientRect()
        const h = card.offsetHeight || 140
        if (narrow) {
          // בטלפון הפעולות החשובות בתחתית (ניווט, שמירה) — הכרטיס למעלה,
          // אלא אם היעד עצמו למעלה.
          apply(r.top > 240 ? { insetInline: 12, top: 76 } : { insetInline: 12, bottom: 84 })
        } else {
          const w = card.offsetWidth || 300
          const below = window.innerHeight - r.bottom > h + 24
          const top = Math.round(below ? r.bottom + 12 : Math.max(12, r.top - h - 12))
          const left = Math.round(Math.min(Math.max(12, r.right - w), window.innerWidth - w - 12))
          apply({ top, left })
        }
      }
      raf = window.requestAnimationFrame(place)
    }
    place()
    return () => window.cancelAnimationFrame(raf)
  }, [target, phase])

  // Escape — יציאה מההדרכה.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onExit(phaseRef.current?.kind === 'done' ? 'completed' : 'abandoned')
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onExit])

  if (!phase) return null
  const stepText = step ? renderText(step.text, text) : null

  return (
    <div
      ref={cardRef}
      className="help-coach"
      style={pos}
      role="dialog"
      aria-modal="false"
      aria-label={t.tourLabel}
      dir="rtl"
    >
      <p className="help-coach-kicker">{t.tourLabel}</p>
      {phase.kind === 'running' && (
        <>
          {/* שורת ההדרכה מוצגת רק כשהיעד באמת נמצא וגלוי — לא "לחצו על X"
              כש-X עוד לא על המסך. */}
          <p className="help-coach-text" aria-live="polite">
            {target ? stepText ?? '' : t.loading}
          </p>
          <div className="help-coach-actions">
            {step?.advanceOn.kind === 'manual' && target && (
              <button type="button" className="btn-primary help-btn-sm" onClick={() => advanceFrom(phase.index + 1)}>
                {t.tourNext}
              </button>
            )}
            <button type="button" className="btn-text help-btn-sm" onClick={() => onExit('abandoned')}>
              {t.tourExit}
            </button>
          </div>
        </>
      )}
      {phase.kind === 'done' && (
        <>
          <p className="help-coach-text" aria-live="polite">{renderText(flow.doneText, text) ?? ''}</p>
          {flow.sendsMessages && mockMode && <p className="help-note">{MOCK_NOTICE}</p>}
          <div className="help-coach-actions">
            <button type="button" className="btn-primary help-btn-sm" onClick={() => onExit('completed')}>
              {t.tourDone}
            </button>
          </div>
        </>
      )}
      {phase.kind === 'notfound' && (
        <>
          <p className="help-coach-text" aria-live="polite">{t.tourNotFound}</p>
          <div className="help-coach-actions">
            <button type="button" className="btn-text help-btn-sm" onClick={() => onExit('failed')}>
              {strings.common.close}
            </button>
          </div>
        </>
      )}
      {phase.kind === 'error' && (
        <>
          <p className="help-coach-text" aria-live="polite">{t.tourError}</p>
          <div className="help-coach-actions">
            <button type="button" className="btn-primary help-btn-sm" onClick={() => onOpenTree(phase.tree)}>
              {t.check}
            </button>
            <button type="button" className="btn-text help-btn-sm" onClick={() => onExit('failed')}>
              {t.tourExit}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
