import type { ReactElement } from 'react'
import type { EventStage, Postponement } from '../types'
import { strings } from '../strings/he'

const t = strings.postpone.banner

/**
 * באנר מצב האירוע — "איפה אנחנו עכשיו, ומה השלב הבא".
 *
 * **מקור המצב הוא השרת.** ``event_stage`` מגיע מוכן מ-``GET /event``
 * (backend/app/postponement_service.py) — הרכיב הזה רק בוחר טקסט, ואינו
 * מסיק מצב בעצמו מצירוף של דגלים. כך אין סיכוי שהמסך יראה מצב אחד
 * והשרת יאכוף אחר.
 *
 * במצב ``normal`` הבאנר לא מוצג כלל: אירוע שמתנהל כרגיל לא צריך שיסבירו לו
 * שהוא מתנהל כרגיל.
 */
export function EventStateBanner({
  stage,
  postponement,
  action,
}: {
  stage: EventStage
  /** נדרש רק כדי להציג סיבת דחייה של בקשה שלא אושרה. */
  postponement?: Postponement | null
  /** הפעולה הבאה, כשיש כזו (למשל "פתיחת מחזור חדש"). */
  action?: React.ReactNode
}) {
  // בקשה שנדחתה אינה "שלב" של האירוע (הוא חזר לשגרה) — אבל הזוג כן צריך
  // לדעת שהיא נדחתה ולמה, אחרת הוא ממתין לתשובה שכבר הגיעה.
  if (stage === 'normal') {
    if (postponement?.status !== 'rejected' || !postponement.rejection_reason) {
      return null
    }
    return (
      <div className="ev-state ev-state-quiet" role="status">
        <span className="ev-state-icon" aria-hidden="true">·</span>
        <div className="ev-state-text">
          <strong className="ev-state-title">{t.rejectedTitle}</strong>
          <p className="ev-state-body">
            {t.rejectedBody(postponement.rejection_reason)}
          </p>
        </div>
      </div>
    )
  }

  // אייקוני מצב האירוע — SVG קווי ולא אימוג'י (⏳/🟠), כדי שהם ייצבעו
  // לפי ה-tone של הבאנר במקום להישאר בצבע של מערכת ההפעלה.
  const ICON: Record<string, ReactElement> = {
    wait: (
      <>
        <circle cx="12" cy="12" r="8.5" />
        <path d="M12 7.4V12l3.2 2" />
      </>
    ),
    open: (
      <>
        <circle cx="12" cy="12" r="8.5" />
        <path d="M12 7.6v5.2M12 16.2v.2" />
      </>
    ),
    done: <path d="M5.5 12.5 10 17l8.5-9" />,
  }

  const copy: Record<
    Exclude<EventStage, 'normal'>,
    { icon: keyof typeof ICON; title: string; body: string; tone: string }
  > = {
    requested: {
      icon: 'wait',
      title: t.requestedTitle,
      body: t.requestedBody,
      tone: 'ev-state-wait',
    },
    open: {
      icon: 'open',
      title: t.openTitle,
      body: t.openBody,
      tone: 'ev-state-open',
    },
    new_date_set: {
      icon: 'open',
      title: t.newDateTitle,
      body: t.newDateBody,
      tone: 'ev-state-open',
    },
    rsvp_reopened: {
      icon: 'done',
      title: t.reopenedTitle,
      body: t.reopenedBody,
      tone: 'ev-state-done',
    },
  }

  const c = copy[stage]
  return (
    <div className={`ev-state ${c.tone}`} role="status">
      <span className="ev-state-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          {ICON[c.icon]}
        </svg>
      </span>
      <div className="ev-state-text">
        <strong className="ev-state-title">{c.title}</strong>
        <p className="ev-state-body">{c.body}</p>
      </div>
      {action && <div className="ev-state-action">{action}</div>}
    </div>
  )
}
