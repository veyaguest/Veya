import { useCallback, useEffect, useRef, useState } from 'react'
import { generateSeating, getHall, saveHall } from '../api'
import type { HallElement, HallElementType, HallGuest, HallState } from '../types'
import { SIDE_LABELS } from '../types'

interface TableView {
  table_number: number
  x: number
  y: number
  guests: HallGuest[]
}

const TABLE_W = 172

// הגדרות ברירת-מחדל לכל סוג אלמנט מיוחד (תווית + גודל).
const ELEMENT_DEFS: Record<
  HallElementType,
  { label: string; width: number; height: number }
> = {
  head_table: { label: 'שולחן ראש', width: 190, height: 74 },
  dance_floor: { label: 'רחבת ריקודים', width: 230, height: 170 },
  bar: { label: 'בר', width: 150, height: 60 },
  stage: { label: 'במה', width: 200, height: 74 },
  dj: { label: 'DJ', width: 96, height: 74 },
  entrance: { label: 'כניסה', width: 100, height: 44 },
}

const ELEMENT_ORDER: HallElementType[] = [
  'head_table',
  'dance_floor',
  'bar',
  'stage',
  'dj',
  'entrance',
]

export function HallPage() {
  const [tables, setTables] = useState<TableView[]>([])
  const [unassigned, setUnassigned] = useState<HallGuest[]>([])
  const [elements, setElements] = useState<HallElement[]>([])
  const [seats, setSeats] = useState(12)
  const [warnings, setWarnings] = useState<string[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [dirty, setDirty] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // גרירת פריט (שולחן או אלמנט) — pointer
  const dragRef = useRef<{
    kind: 'table' | 'element'
    id: number | string
    dx: number
    dy: number
  } | null>(null)
  const canvasRef = useRef<HTMLDivElement | null>(null)

  const applyState = useCallback((h: HallState) => {
    setTables(
      h.tables.map((t) => ({
        table_number: t.table_number,
        x: t.x,
        y: t.y,
        guests: t.guests,
      })),
    )
    setUnassigned(h.unassigned)
    setElements(h.elements ?? [])
    setSeats(h.seats_per_table)
    setWarnings(h.warnings)
    setDirty(false)
  }, [])

  const load = useCallback(async () => {
    setError('')
    try {
      applyState(await getHall())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בטעינת מפת האולם')
    }
  }, [applyState])

  useEffect(() => {
    load()
  }, [load])

  // ---- גרירת שולחן / אלמנט ----
  function onTablePointerDown(e: React.PointerEvent, tnum: number) {
    const t = tables.find((x) => x.table_number === tnum)
    if (!t || !canvasRef.current) return
    const rect = canvasRef.current.getBoundingClientRect()
    dragRef.current = {
      kind: 'table',
      id: tnum,
      dx: e.clientX - rect.left - t.x,
      dy: e.clientY - rect.top - t.y,
    }
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
  }

  function onElementPointerDown(e: React.PointerEvent, id: string) {
    const el = elements.find((x) => x.id === id)
    if (!el || !canvasRef.current) return
    const rect = canvasRef.current.getBoundingClientRect()
    dragRef.current = {
      kind: 'element',
      id,
      dx: e.clientX - rect.left - el.x,
      dy: e.clientY - rect.top - el.y,
    }
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
  }

  function onCanvasPointerMove(e: React.PointerEvent) {
    const drag = dragRef.current
    if (!drag || !canvasRef.current) return
    const rect = canvasRef.current.getBoundingClientRect()
    const x = Math.max(0, e.clientX - rect.left - drag.dx)
    const y = Math.max(0, e.clientY - rect.top - drag.dy)
    if (drag.kind === 'table') {
      setTables((prev) =>
        prev.map((t) => (t.table_number === drag.id ? { ...t, x, y } : t)),
      )
    } else {
      setElements((prev) =>
        prev.map((el) => (el.id === drag.id ? { ...el, x, y } : el)),
      )
    }
    setDirty(true)
  }

  function onCanvasPointerUp() {
    dragRef.current = null
  }

  function addElement(type: HallElementType) {
    const def = ELEMENT_DEFS[type]
    const el: HallElement = {
      id: `${type}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      type,
      x: 80,
      y: 80,
      width: def.width,
      height: def.height,
      label: def.label,
    }
    setElements((prev) => [...prev, el])
    setDirty(true)
  }

  function removeElement(id: string) {
    setElements((prev) => prev.filter((el) => el.id !== id))
    setDirty(true)
  }

  // ---- העברת מוזמן ----
  function moveGuestToTable(guestId: number, targetTable: number | null) {
    let moving: HallGuest | undefined
    // הסרה ממיקום נוכחי
    const nextTables = tables.map((t) => {
      const found = t.guests.find((g) => g.id === guestId)
      if (found) moving = found
      return { ...t, guests: t.guests.filter((g) => g.id !== guestId) }
    })
    let nextUnassigned = unassigned.filter((g) => g.id !== guestId)
    if (!moving) moving = unassigned.find((g) => g.id === guestId)
    if (!moving) return

    if (targetTable === null) {
      nextUnassigned = [...nextUnassigned, moving]
    } else {
      const idx = nextTables.findIndex((t) => t.table_number === targetTable)
      if (idx >= 0) nextTables[idx] = { ...nextTables[idx], guests: [...nextTables[idx].guests, moving] }
    }
    setTables(nextTables)
    setUnassigned(nextUnassigned)
    setSelected(null)
    setDirty(true)
  }

  function onGuestClick(e: React.MouseEvent, guestId: number) {
    e.stopPropagation()
    setSelected((cur) => (cur === guestId ? null : guestId))
  }

  function onTableClick(tnum: number) {
    if (selected !== null) moveGuestToTable(selected, tnum)
  }

  function onTrayClick() {
    if (selected !== null) moveGuestToTable(selected, null)
  }

  async function onSave() {
    setLoading(true)
    setError('')
    try {
      const payload = tables.map((t) => ({
        table_number: t.table_number,
        x: t.x,
        y: t.y,
        guest_ids: t.guests.map((g) => g.id),
      }))
      applyState(await saveHall(payload, seats, elements))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בשמירת המפה')
    } finally {
      setLoading(false)
    }
  }

  async function onRegenerate() {
    setLoading(true)
    setError('')
    try {
      const res = await generateSeating({ seats_per_table: seats, persist: true })
      if (!res.hard_ok) {
        setError('השיבוץ האוטומטי לא הצליח לשמור על כל החוקים — נסה יותר כיסאות לשולחן.')
      }
      applyState(await getHall())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה ביצירת שיבוץ')
    } finally {
      setLoading(false)
    }
  }

  const canvasHeight = Math.max(
    460,
    ...tables.map((t) => t.y + 220),
  )

  return (
    <div className="hall-page">
      <div className="hall-toolbar">
        <label className="seats-field">
          כיסאות לשולחן
          <input
            type="number"
            min={1}
            value={seats}
            onChange={(e) => setSeats(Math.max(1, Number(e.target.value) || 1))}
          />
        </label>
        <button className="btn-ghost" onClick={onRegenerate} disabled={loading}>
          ↻ שיבוץ אוטומטי מחדש
        </button>
        <button className="btn-primary" onClick={onSave} disabled={loading || !dirty}>
          {loading ? 'שומר…' : dirty ? 'שמור מפה' : 'נשמר ✓'}
        </button>
        <span className="hall-hint">
          גררו שולחן להזזה · לחצו על מוזמן ואז על שולחן כדי להעביר אותו
        </span>
      </div>

      <div className="hall-palette">
        <span className="palette-label">הוסף למפה:</span>
        {ELEMENT_ORDER.map((type) => (
          <button
            key={type}
            type="button"
            className="palette-btn"
            onClick={() => addElement(type)}
          >
            + {ELEMENT_DEFS[type].label}
          </button>
        ))}
      </div>

      {error && <p className="form-error">{error}</p>}

      {warnings.length > 0 && (
        <div className="hall-warnings">
          {warnings.map((w, i) => (
            <p key={i}>⚠ {w}</p>
          ))}
        </div>
      )}

      <div className="hall-layout">
        {/* מגש מוזמנים ללא שולחן */}
        <div
          className={`hall-tray ${selected !== null ? 'droppable' : ''}`}
          onClick={onTrayClick}
        >
          <h4 className="tray-title">ללא שולחן ({unassigned.length})</h4>
          {unassigned.length === 0 && <p className="tray-empty">כולם משובצים ✓</p>}
          {unassigned.map((g) => (
            <GuestChip
              key={g.id}
              g={g}
              selected={selected === g.id}
              onClick={(e) => onGuestClick(e, g.id)}
            />
          ))}
        </div>

        {/* קנבס מפת האולם */}
        <div
          className="hall-canvas"
          ref={canvasRef}
          style={{ height: canvasHeight }}
          onPointerMove={onCanvasPointerMove}
          onPointerUp={onCanvasPointerUp}
          onPointerLeave={onCanvasPointerUp}
        >
          {tables.length === 0 && elements.length === 0 && (
            <p className="hall-empty">
              אין עדיין שולחנות. לחצו "שיבוץ אוטומטי מחדש" כדי לחלק את המוזמנים.
            </p>
          )}
          {elements.map((el) => (
            <div
              key={el.id}
              className={`hall-element el-${el.type}`}
              style={{ left: el.x, top: el.y, width: el.width, height: el.height }}
              onPointerDown={(e) => onElementPointerDown(e, el.id)}
            >
              <span className="element-label">{el.label}</span>
              <button
                type="button"
                className="element-del"
                title="הסר"
                onPointerDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  e.stopPropagation()
                  removeElement(el.id)
                }}
              >
                ×
              </button>
            </div>
          ))}
          {tables.map((t) => {
            const used = t.guests.reduce((s, g) => s + g.party_size, 0)
            const over = used > seats
            return (
              <div
                key={t.table_number}
                className={`hall-table ${over ? 'over' : ''} ${
                  selected !== null ? 'droppable' : ''
                }`}
                style={{ left: t.x, top: t.y, width: TABLE_W }}
                onClick={() => onTableClick(t.table_number)}
              >
                <div
                  className="table-disc"
                  onPointerDown={(e) => onTablePointerDown(e, t.table_number)}
                >
                  <SeatRing seats={seats} guests={t.guests} />
                  <span className="table-center">
                    <span className="table-num">{t.table_number}</span>
                    <span className="table-occ">
                      {used}/{seats}
                    </span>
                  </span>
                </div>
                <div className="hall-table-body">
                  {t.guests.map((g) => (
                    <GuestChip
                      key={g.id}
                      g={g}
                      selected={selected === g.id}
                      onClick={(e) => onGuestClick(e, g.id)}
                    />
                  ))}
                  {t.guests.length === 0 && (
                    <span className="table-empty-hint">ריק</span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// טבעת כיסאות מסביב לדיסקת השולחן: תפוס נצבע לפי צד, פנוי נשאר חלול.
function SeatRing({ seats, guests }: { seats: number; guests: HallGuest[] }) {
  // הרחבת החבורות לכיסאות בודדים (לפי party_size), לצביעה לפי צד.
  const occupied: string[] = []
  for (const g of guests) {
    for (let i = 0; i < g.party_size; i++) occupied.push(g.side)
  }
  const count = Math.max(seats, occupied.length, 1)
  const radius = 44
  return (
    <span className="seat-ring" aria-hidden="true">
      {Array.from({ length: count }).map((_, i) => {
        const side = occupied[i]
        const angle = (i / count) * 360
        return (
          <span
            key={i}
            className={`seat-pip ${side ? `seat-${side}` : 'seat-free'} ${
              i >= seats ? 'seat-extra' : ''
            }`}
            style={{
              transform: `rotate(${angle}deg) translateY(-${radius}px) rotate(-${angle}deg)`,
            }}
          />
        )
      })}
    </span>
  )
}

function GuestChip({
  g,
  selected,
  onClick,
}: {
  g: HallGuest
  selected: boolean
  onClick: (e: React.MouseEvent) => void
}) {
  return (
    <span
      className={`guest-chip side-${g.side} ${selected ? 'selected' : ''}`}
      onClick={onClick}
      title={SIDE_LABELS[g.side]}
    >
      {g.full_name}
      {g.party_size > 1 && <span className="chip-size">×{g.party_size}</span>}
    </span>
  )
}
