/**
 * העזרה עצמה — חלונית קטנה + הדרכות (HELP_CENTER_PLAN.md שלב 4). נטען עצל.
 *
 * עקרונות (החלטות המייסד 2026-09-29):
 * - לא צ'אט: עד 4 שאלות לפי המסך והמצב, "משהו לא עובד", וחיפוש. זהו.
 * - תשובה קצרה → פעולה אחת ("תראו לי" / "בואו נבדוק" / מעבר / מדריך).
 * - כל מה שמוצג נשען על עובדות אמיתיות: דפדפן + ``/help/context/{screen}``
 *   + בדיקה על מוזמן שנבחר. לא ידוע → לא מוצג / "לא הצלחנו לבדוק".
 * - WhatsApp במצב הדגמה → הודעה כנה ליד כל מה שמדבר על שליחה.
 * - שום פעולה כאן לא משנה נתונים. אין שליחה, אין שמירה, אין מחיקה.
 * - צוות VEYA עוד לא מוצג (שלב 7): קודם תשובה → הדרכה → בדיקה → ניסיון נוסף.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getHelpContext, getHelpGuestCheck, getHelpGuestOptions } from '../../api'
import { useBackToClose } from '../../lib/backToClose'
import { useFocusTrap } from '../../lib/useFocusTrap'
import { useMediaQuery } from '../../lib/useMediaQuery'
import { getEventTerms } from '../../strings/eventTypes'
import { strings } from '../../strings/he'
import type { EventSummary } from '../../types'
import { closeHelp, openHelp } from '../helpStore'
import { requestGuide } from '../bridge'
import { GUIDES } from '../guides'
import type { Facts } from '../facts'
import type { HelpPage } from '../targets'
import type { DiagnosticTree, GuestFilter, HelpAction, HelpTopic } from '../types'
import { activeScopes, subscribeScopes } from '../scopes'
import { recentErrors } from '../errorBus'
import { FLOWS, TOPICS, TREES } from '../kb/index'
import { MOCK_NOTICE } from '../kb/shared'
import { holds } from '../engine/conditions'
import { runTree } from '../engine/diagnose'
import { canStartFlow } from '../engine/flows'
import { search } from '../engine/search'
import { renderText } from '../engine/text'
import type { TextContext } from '../engine/text'
import {
  errorFactsFor, messagingMode, rankTopics, resolveTopic, scopeScore, treeForRecentError,
} from '../engine/topics'
import type { ResolvedAction } from '../engine/topics'
import { clientFacts, serverFacts } from './facts'
import TourRunner from './TourRunner'
import './help.css'

export interface HelpAppProps {
  open: boolean
  page: HelpPage
  /** שם המסך כפי שמוצג בכותרת האפליקציה. */
  screenTitle: string
  /** מעבר מסך. ``fresh`` — טעינה מחדש של המסך גם כשכבר נמצאים בו (סינון מוכן). */
  goTo: (page: HelpPage, options?: { guestFilter?: GuestFilter; fresh?: boolean }) => void
  event: EventSummary
  online: boolean | null
}

type View =
  | { kind: 'home' }
  | { kind: 'topic'; id: string }
  | { kind: 'trouble' }
  | { kind: 'tree'; id: string }

const t = strings.help
const CONTEXT_TTL_MS = 60_000

function useScopes() {
  const [scopes, setScopes] = useState(activeScopes)
  useEffect(() => subscribeScopes(() => setScopes(activeScopes())), [])
  return scopes
}

export default function HelpApp({ open, page, screenTitle, goTo, event, online }: HelpAppProps) {
  const isNarrow = useMediaQuery('(max-width: 820px)')
  const scopes = useScopes()
  const [stack, setStack] = useState<View[]>([{ kind: 'home' }])
  const view = stack[stack.length - 1]
  const [query, setQuery] = useState('')
  const [notHelped, setNotHelped] = useState<Set<string>>(new Set())
  const [tour, setTour] = useState<string | null>(null)

  // ── עובדות השרת למסך הנוכחי (עם מטמון קצר) ──
  const [server, setServer] = useState<{ page: HelpPage; at: number; facts: Facts } | null>(null)
  const [contextError, setContextError] = useState(false)
  const loadContext = useCallback(
    async (force = false) => {
      if (!force && server && server.page === page && Date.now() - server.at < CONTEXT_TTL_MS) return
      try {
        const res = await getHelpContext(page)
        setServer({ page, at: Date.now(), facts: serverFacts(res.facts) })
        setContextError(false)
      } catch {
        setContextError(true)
      }
    },
    [page, server],
  )
  useEffect(() => {
    if (open) void loadContext()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, page])
  const serverReady = server?.page === page

  const facts = useCallback(
    (): Facts => ({ ...(serverReady ? server!.facts : {}), ...clientFacts(event, online) }),
    [server, serverReady, event, online],
  )
  const text: TextContext = useMemo(() => {
    const terms = getEventTerms(event.event_type)
    return {
      facts: facts(),
      terms: {
        guests: terms.guestsLabel,
        guest: terms.guestsLabel === 'משתתפים' ? 'משתתף' : 'מוזמן',
        hosts: terms.hostsLabel,
        event: terms.eventNoun,
      },
      ui: (path: string) => {
        let cur: unknown = strings
        for (const k of path.split('.')) cur = cur && typeof cur === 'object' ? (cur as Record<string, unknown>)[k] : undefined
        return typeof cur === 'string' ? cur : undefined
      },
    }
    // scopes: עובדות הלקוח (למשל שלב באשף) משתנות עם המסך
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [facts, event.event_type, scopes])
  const mockMode = messagingMode(text.facts) === 'mock'

  // ── פתיחה/סגירה: פוקוס, "חזור" בטלפון, Escape ──
  const panelRef = useRef<HTMLDivElement | null>(null)
  const titleRef = useRef<HTMLHeadingElement | null>(null)
  const showPanel = open && !tour
  useBackToClose(showPanel && isNarrow, closeHelp)
  useFocusTrap(panelRef, showPanel && isNarrow)
  useEffect(() => {
    if (!showPanel) return
    titleRef.current?.focus()
    return () => {
      // הפוקוס חוזר לכפתור העזרה (אם ההדרכה לא לקחה אותו).
      if (!tour) document.querySelector<HTMLElement>('[data-help-launcher]')?.focus()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showPanel])
  useEffect(() => {
    if (!open) {
      setStack([{ kind: 'home' }])
      setQuery('')
    }
  }, [open])

  const push = (v: View) => setStack((s) => [...s, v])
  const back = () => setStack((s) => (s.length > 1 ? s.slice(0, -1) : s))

  // ── פעולות: אף אחת מהן לא משנה נתונים ──
  function runAction(a: HelpAction) {
    if (a.kind === 'diagnose') return push({ kind: 'tree', id: a.tree })
    if (a.kind === 'tour') {
      setTour(a.flow)
      closeHelp()
      return
    }
    if (a.kind === 'navigate') {
      goTo(a.page, { guestFilter: a.guestFilter, fresh: !!a.guestFilter })
      closeHelp()
      return
    }
    const guide = GUIDES[a.guide]
    if (page !== guide.page) goTo(guide.page)
    requestGuide(a.guide)
    closeHelp()
  }

  function actionLabel(r: ResolvedAction): string {
    if (r.label) return r.label
    if (r.action.kind === 'tour') return t.showMe
    if (r.action.kind === 'diagnose') return t.check
    if (r.action.kind === 'guide') return t.guide
    return ''
  }

  const now = Date.now()
  const errors = recentErrors()
  const flows = FLOWS
  const rankCtx = { scopes, facts: text.facts, text, recentErrors: errors, now, notHelped, flows }
  const home = useMemo(() => rankTopics(TOPICS, rankCtx), [text, scopes, notHelped, errors.length]) // eslint-disable-line react-hooks/exhaustive-deps
  const errorTree = useMemo(() => treeForRecentError(TREES, { facts: text.facts, recentErrors: errors, now }), [text, errors.length]) // eslint-disable-line react-hooks/exhaustive-deps

  const treeVisible = (tr: DiagnosticTree) =>
    holds(tr.when, text.facts) && (!tr.sendsMessages || messagingMode(text.facts) !== null)
  const troubleTrees = TREES.filter((tr) => treeVisible(tr) && scopeScore(tr.scopes, scopes) > 0)
    .sort((a, b) => scopeScore(b.scopes, scopes) - scopeScore(a.scopes, scopes))
    .slice(0, 4)

  const searchResults = useMemo(() => {
    if (query.trim().length < 2) return null
    const topics = TOPICS.filter((x) => resolveTopic(x, { facts: text.facts, text, flows }) !== null)
    const trees = TREES.filter(treeVisible)
    const items = [
      ...topics.map((x) => ({ id: `t:${x.id}`, texts: [renderText(x.title, text) ?? '', ...x.aliases] })),
      ...trees.map((x) => ({ id: `d:${x.id}`, texts: [renderText(x.symptom, text) ?? ''] })),
    ]
    return search(query, items).slice(0, 6)
  }, [query, text]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── הדרכה פעילה: רק הכרטיס הקטן, בלי החלונית ──
  const onTourStart = useCallback(
    (flow: { start: { page: HelpPage; guestFilter?: GuestFilter } }) => {
      goTo(flow.start.page, { guestFilter: flow.start.guestFilter, fresh: !!flow.start.guestFilter })
    },
    [goTo],
  )
  const onTourExit = useCallback(() => {
    setTour(null)
    void loadContext(true)
  }, [loadContext])
  const onTourTree = useCallback((treeId: string) => {
    setTour(null)
    setStack([{ kind: 'home' }, { kind: 'tree', id: treeId }])
    openHelp()
  }, [])

  const tourFlow = tour ? FLOWS[tour] : null

  return (
    <>
      {tourFlow && (
        <TourRunner
          flow={tourFlow}
          facts={facts}
          text={text}
          mockMode={mockMode}
          onStart={onTourStart}
          onExit={onTourExit}
          onOpenTree={onTourTree}
        />
      )}
      {showPanel && (
        <>
          {isNarrow && <div className="help-backdrop" onClick={closeHelp} aria-hidden="true" />}
          <div
            id="veya-help-panel"
            ref={panelRef}
            className="help-panel"
            role="dialog"
            aria-modal={isNarrow}
            aria-labelledby="veya-help-title"
            dir="rtl"
            tabIndex={-1}
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                e.stopPropagation()
                closeHelp()
              }
            }}
          >
            <header className="help-head">
              {stack.length > 1 && (
                <button type="button" className="help-icon-btn" onClick={back} aria-label={t.back}>
                  <span aria-hidden="true">→</span>
                </button>
              )}
              <h2 id="veya-help-title" className="help-title" ref={titleRef} tabIndex={-1}>
                {t.panelTitle}
                <span className="help-subtitle">{screenTitle}</span>
              </h2>
              <button type="button" className="help-icon-btn" onClick={closeHelp} aria-label={t.close}>
                <span aria-hidden="true">✕</span>
              </button>
            </header>

            <div className="help-body">
              {!serverReady && !contextError && <p className="help-muted">{t.loading}</p>}
              {contextError && (
                <p className="help-note">
                  {t.contextError}{' '}
                  <button type="button" className="btn-text help-inline-btn" onClick={() => void loadContext(true)}>
                    {strings.common.retry}
                  </button>
                </p>
              )}

              {view.kind === 'home' && (serverReady || contextError) && (
                <HomeView
                  query={query}
                  onQuery={setQuery}
                  results={searchResults}
                  home={home}
                  errorTree={errorTree}
                  text={text}
                  onTopic={(id) => push({ kind: 'topic', id })}
                  onTree={(id) => push({ kind: 'tree', id })}
                  onTrouble={() => push({ kind: 'trouble' })}
                />
              )}

              {view.kind === 'topic' && (
                <TopicView
                  topic={TOPICS.find((x) => x.id === view.id)!}
                  ctx={{ facts: text.facts, text, flows }}
                  mockMode={mockMode}
                  actionLabel={actionLabel}
                  onAction={runAction}
                  onTopic={(id) => push({ kind: 'topic', id })}
                  onTrouble={() => push({ kind: 'trouble' })}
                  onNotHelped={(id) => setNotHelped((s) => new Set(s).add(id))}
                />
              )}

              {view.kind === 'trouble' && (
                <div className="help-section">
                  <h3 className="help-h3">{t.somethingWrongTitle}</h3>
                  {troubleTrees.length === 0 && <p className="help-muted">{t.noTrouble}</p>}
                  <ul className="help-list">
                    {troubleTrees.map((tr) => (
                      <li key={tr.id}>
                        <button type="button" className="help-item" onClick={() => push({ kind: 'tree', id: tr.id })}>
                          {renderText(tr.symptom, text)}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {view.kind === 'tree' && (
                <TreeView
                  key={view.id}
                  tree={TREES.find((x) => x.id === view.id)!}
                  baseFacts={text.facts}
                  text={text}
                  mockMode={mockMode}
                  actionLabel={actionLabel}
                  onAction={runAction}
                  canRunAction={(a) => a.kind !== 'tour' || canStartFlow(FLOWS[a.flow], text.facts)}
                />
              )}
            </div>
          </div>
        </>
      )}
    </>
  )
}

// ─── הבית ───────────────────────────────────────────────────────────────────

function HomeView({
  query, onQuery, results, home, errorTree, text, onTopic, onTree, onTrouble,
}: {
  query: string
  onQuery: (q: string) => void
  results: string[] | null
  home: ReturnType<typeof rankTopics>
  errorTree: DiagnosticTree | null
  text: TextContext
  onTopic: (id: string) => void
  onTree: (id: string) => void
  onTrouble: () => void
}) {
  const titleOf = (id: string) => {
    if (id.startsWith('t:')) {
      const topic = TOPICS.find((x) => x.id === id.slice(2))
      return topic ? renderText(topic.title, text) : null
    }
    const tree = TREES.find((x) => x.id === id.slice(2))
    return tree ? renderText(tree.symptom, text) : null
  }
  return (
    <>
      <label className="help-search">
        <span className="help-visually-hidden">{t.searchLabel}</span>
        <input
          type="search"
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          placeholder={t.searchPlaceholder}
          aria-label={t.searchLabel}
        />
      </label>

      {results !== null ? (
        <div className="help-section" aria-live="polite">
          {results.length === 0 && <p className="help-muted">{t.searchEmpty}</p>}
          <ul className="help-list">
            {results.map((id) => (
              <li key={id}>
                <button
                  type="button"
                  className="help-item"
                  onClick={() => (id.startsWith('t:') ? onTopic(id.slice(2)) : onTree(id.slice(2)))}
                >
                  {titleOf(id)}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <>
          {errorTree && (
            <div className="help-card help-card-alert">
              <p className="help-card-kicker">{t.recentError}</p>
              <p className="help-card-title">{renderText(errorTree.symptom, text)}</p>
              <button type="button" className="btn-primary help-btn-sm" onClick={() => onTree(errorTree.id)}>
                {t.recentErrorCta}
              </button>
            </div>
          )}
          {home.urgent && (
            <button type="button" className="help-card help-card-urgent" onClick={() => onTopic(home.urgent!.topic.id)}>
              <span className="help-card-kicker">{t.urgentLabel}</span>
              <span className="help-card-title">{home.urgent.title}</span>
            </button>
          )}
          {home.topics.length === 0 && !home.urgent && <p className="help-muted">{t.noTopics}</p>}
          <ul className="help-list">
            {home.topics.map((r) => (
              <li key={r.topic.id}>
                <button type="button" className="help-item" onClick={() => onTopic(r.topic.id)}>
                  {r.title}
                </button>
              </li>
            ))}
          </ul>
          <button type="button" className="help-item help-item-trouble" onClick={onTrouble}>
            {t.somethingWrong}
          </button>
        </>
      )}
    </>
  )
}

// ─── נושא ───────────────────────────────────────────────────────────────────

function TopicView({
  topic, ctx, mockMode, actionLabel, onAction, onTopic, onTrouble, onNotHelped,
}: {
  topic: HelpTopic
  ctx: Parameters<typeof resolveTopic>[1]
  mockMode: boolean
  actionLabel: (r: ResolvedAction) => string
  onAction: (a: HelpAction) => void
  onTopic: (id: string) => void
  onTrouble: () => void
  onNotHelped: (id: string) => void
}) {
  const [feedback, setFeedback] = useState<'none' | 'yes' | 'no'>('none')
  const r = resolveTopic(topic, ctx)
  if (!r) return <p className="help-muted">{t.searchEmpty}</p>
  const related = (topic.related ?? [])
    .map((id) => TOPICS.find((x) => x.id === id))
    .map((x) => (x ? resolveTopic(x, ctx) : null))
    .filter((x): x is NonNullable<typeof x> => x !== null)
  return (
    <div className="help-section">
      <h3 className="help-h3">{r.title}</h3>
      {r.answer.map((line, i) => (
        <p key={i} className="help-answer">{line}</p>
      ))}
      {r.mockNotice && mockMode && <p className="help-note">{MOCK_NOTICE}</p>}
      {r.primary && (
        <button type="button" className="btn-primary help-primary" onClick={() => onAction(r.primary!.action)}>
          {actionLabel(r.primary)}
        </button>
      )}

      {related.length > 0 && (
        <div className="help-related">
          <p className="help-small-title">{t.related}</p>
          <ul className="help-list">
            {related.map((x) => (
              <li key={x.topic.id}>
                <button type="button" className="help-item help-item-quiet" onClick={() => onTopic(x.topic.id)}>
                  {x.title}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <Feedback
        state={feedback}
        onYes={() => setFeedback('yes')}
        onNo={() => {
          setFeedback('no')
          onNotHelped(topic.id)
        }}
      />
      {feedback === 'no' && (
        <div className="help-next">
          <p className="help-small-title">{t.nextTry}</p>
          <ul className="help-list">
            {r.primary?.action.kind === 'tour' && (
              <li>
                <button type="button" className="help-item help-item-quiet" onClick={() => onAction(r.primary!.action)}>
                  {actionLabel(r.primary)}
                </button>
              </li>
            )}
            <li>
              <button type="button" className="help-item help-item-quiet" onClick={onTrouble}>
                {t.somethingWrong}
              </button>
            </li>
          </ul>
        </div>
      )}
    </div>
  )
}

function Feedback({ state, onYes, onNo }: { state: 'none' | 'yes' | 'no'; onYes: () => void; onNo: () => void }) {
  if (state === 'yes') return <p className="help-muted help-feedback" role="status">{t.feedbackThanks}</p>
  if (state === 'no') return null
  return (
    <div className="help-feedback" role="group" aria-label={t.feedbackQuestion}>
      <span>{t.feedbackQuestion}</span>
      <button type="button" className="btn-ghost help-btn-sm" onClick={onYes}>{t.feedbackYes}</button>
      <button type="button" className="btn-ghost help-btn-sm" onClick={onNo}>{t.feedbackNo}</button>
    </div>
  )
}

// ─── בדיקת תקלה ────────────────────────────────────────────────────────────

function TreeView({
  tree, baseFacts, text, mockMode, actionLabel, onAction, canRunAction,
}: {
  tree: DiagnosticTree
  baseFacts: Facts
  text: TextContext
  mockMode: boolean
  actionLabel: (r: ResolvedAction) => string
  onAction: (a: HelpAction) => void
  canRunAction: (a: HelpAction) => boolean
}) {
  const [answers, setAnswers] = useState<Record<string, number>>({})
  const [guest, setGuest] = useState<{ id: number; name: string } | null>(null)
  const [guestFacts, setGuestFacts] = useState<Facts | null>(null)
  const [checkError, setCheckError] = useState(false)
  const [feedback, setFeedback] = useState<'none' | 'yes' | 'no'>('none')

  useEffect(() => {
    if (!guest) return
    let alive = true
    setGuestFacts(null)
    setCheckError(false)
    getHelpGuestCheck(tree.id, guest.id)
      .then((res) => alive && setGuestFacts(serverFacts(res.facts)))
      .catch(() => alive && setCheckError(true))
    return () => {
      alive = false
    }
  }, [guest, tree.id])

  const title = renderText(tree.symptom, text)
  if (tree.needsGuest && !guest) {
    return (
      <div className="help-section">
        <h3 className="help-h3">{title}</h3>
        <GuestPicker guestLabel={text.terms.guest} onPick={setGuest} />
      </div>
    )
  }
  if (tree.needsGuest && !guestFacts) {
    return (
      <div className="help-section">
        <h3 className="help-h3">{title}</h3>
        <p className={checkError ? 'help-note' : 'help-muted'}>{checkError ? t.checkError : t.checking}</p>
      </div>
    )
  }

  const facts: Facts = {
    ...baseFacts,
    ...errorFactsFor(tree.errorMatch, recentErrors(), Date.now()),
    ...(guestFacts ?? {}),
  }
  const { step } = runTree(tree, facts, answers)
  const ctx: TextContext = { ...text, facts }

  return (
    <div className="help-section">
      <h3 className="help-h3">{title}</h3>
      {guest && <p className="help-muted">{guest.name}</p>}

      {step.kind === 'ask' && (
        <>
          <p className="help-answer">{renderText(step.def.question, ctx)}</p>
          <ul className="help-list">
            {step.def.options.map((o, i) => (
              <li key={i}>
                <button type="button" className="help-item" onClick={() => setAnswers((a) => ({ ...a, [step.node]: i }))}>
                  {renderText(o.label, ctx)}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}

      {step.kind === 'cant-check' && <p className="help-answer">{t.cantCheck}</p>}

      {step.kind === 'outcome' && (
        <>
          {step.def.text.map((line, i) => {
            const r = renderText(line, ctx)
            return r ? <p key={i} className="help-answer">{r}</p> : null
          })}
          {tree.sendsMessages && mockMode && !step.def.text.includes(MOCK_NOTICE) && (
            <p className="help-note">{MOCK_NOTICE}</p>
          )}
          {step.def.action && canRunAction(step.def.action) && (
            <button type="button" className="btn-primary help-primary" onClick={() => onAction(step.def.action!)}>
              {actionLabel({ action: step.def.action, label: step.def.action.label ? renderText(step.def.action.label, ctx) : null })}
            </button>
          )}
          <Feedback state={feedback} onYes={() => setFeedback('yes')} onNo={() => setFeedback('no')} />
        </>
      )}

      {guest && (
        <button
          type="button"
          className="btn-text help-inline-btn"
          onClick={() => {
            setGuest(null)
            setGuestFacts(null)
            setFeedback('none')
          }}
        >
          {t.checkAnother}
        </button>
      )}
    </div>
  )
}

function GuestPicker({ guestLabel, onPick }: { guestLabel: string; onPick: (g: { id: number; name: string }) => void }) {
  const [q, setQ] = useState('')
  const [options, setOptions] = useState<{ id: number; name: string }[] | null>(null)
  const [error, setError] = useState(false)
  useEffect(() => {
    const needle = q.trim()
    if (needle.length < 2) {
      setOptions(null)
      return
    }
    let alive = true
    const id = window.setTimeout(() => {
      getHelpGuestOptions(needle)
        .then((res) => {
          if (!alive) return
          setOptions(res)
          setError(false)
        })
        .catch(() => alive && setError(true))
    }, 250)
    return () => {
      alive = false
      window.clearTimeout(id)
    }
  }, [q])
  return (
    <div className="help-picker">
      <p className="help-answer">{t.whoTitle(guestLabel)}</p>
      <input
        type="search"
        className="help-picker-input"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={t.guestSearchPlaceholder}
        aria-label={t.guestSearchLabel}
        autoFocus
      />
      {error && <p className="help-note">{t.checkError}</p>}
      {options && options.length === 0 && <p className="help-muted">{t.guestNone}</p>}
      {options && options.length > 0 && (
        <ul className="help-list" aria-live="polite">
          {options.map((o) => (
            <li key={o.id}>
              <button type="button" className="help-item" onClick={() => onPick(o)}>
                {o.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
