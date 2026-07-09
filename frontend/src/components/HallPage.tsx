import { useCallback, useEffect, useRef, useState } from 'react'
import { generateSeating, getHall, saveHall } from '../api'
import type { HallGuest, HallState } from '../types'
import { SIDE_LABELS } from '../types'

interface TableView {
  table_number: number
  x: number
  y: number
  guests: HallGuest[]
}

const TABLE_W = 172

export function HallPage() {
  const [tables, setTables] = useState<TableView[]>([])
  const [unassigned, setUnassigned] = useState<HallGuest[]>([])
  const [seats, setSeats] = useState(12)
  const [warnings, setWarnings] = useState<string[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [dirty, setDirty] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // גרירת שולחן (pointer)
  const dragRef = useRef<{ tnum: number; dx: number; dy: number } | null>(null)
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

  // ---- גרירת שולחן ----
  function onTablePointerDown(e: React.PointerEvent, tnum: number) {
    const t = tables.find((x) => x.table_number === tnum)
    if (!t || !canvasRef.current) return
    const rect = canvasRef.current.getBoundingClientRect()
    dragRef.current = {
      tnum,
      dx: e.clientX - rect.left - t.x,
      dy: e.clientY - rect.top - t.y,
    }
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
  }

  function onCanvasPointerMove(e: React.PointerEvent) {
    const drag = dragRef.current
    if (!drag || !canvasRef.current) return
    const rect = canvasRef.current.getBoundingClientRect()
    const x = Math.max(0, e.clientX - rect.left - drag.dx)
    const y = Math.max(0, e.clientY - rect.top - drag.dy)
    setTables((prev) =>
      prev.map((t) => (t.table_number === drag.tnum ? { ...t, x, y } : t)),
    )
    setDirty(true)
  }

  function onCanvasPointerUp() {
    dragRef.current = null
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
      applyState(await saveHall(payload, seats))
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
          {tables.length === 0 && (
            <p className="hall-empty">
              אין עדיין שולחנות. לחצו "שיבוץ אוטומטי מחדש" כדי לחלק את המוזמנים.
            </p>
          )}
          {tables.map((t) => {
            const over = t.guests.reduce((s, g) => s + g.party_size, 0) > seats
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
                  className="hall-table-head"
                  onPointerDown={(e) => onTablePointerDown(e, t.table_number)}
                >
                  <span>שולחן {t.table_number}</span>
                  <span className="hall-occ">
                    {t.guests.reduce((s, g) => s + g.party_size, 0)}/{seats}
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
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
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
