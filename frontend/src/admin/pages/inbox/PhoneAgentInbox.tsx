/**
 * תיבת ה-WhatsApp בתוך מסך הטלפן (החלטת המייסד 2026-10-19: גם הטלפנים עונים).
 *
 * אותו רכיב כמו במרכז השליטה (``InboxView``), עם מצב פנימי במקום ניווט hash,
 * עטוף ב-``.adm-root.wa-embedded`` כדי לקבל את הטוקנים של admin.css בלי
 * הגריד של סרגל הניהול. נטען בעצלתיים — רק כשהטלפן פותח את הלשונית.
 */
import { useState } from 'react'
import type { InboxFilter } from '../../inboxApi'
import { InboxView } from './InboxPage'
import '../../admin.css'

export default function PhoneAgentInbox({ meId }: { meId: number }) {
  const [selected, setSelected] = useState<number | null>(null)
  const [filter, setFilter] = useState<InboxFilter>('open')
  const [mine, setMine] = useState(false)
  return (
    <div className="adm-root wa-embedded" dir="rtl">
      <InboxView
        selectedId={selected}
        filter={filter}
        mine={mine}
        meId={meId}
        onSelect={(id) => {
          setSelected(id)
          window.scrollTo({ top: 0 })
        }}
        onFilter={(f, m) => {
          setFilter(f)
          setMine(m)
        }}
      />
    </div>
  )
}
