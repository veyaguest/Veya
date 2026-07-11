import { useCallback, useEffect, useRef, useState } from 'react'
import {
  analyzeConstraints,
  generateSeating,
  getHall,
  listClarifications,
  resolveClarification,
  saveHall,
} from '../api'
import type {
  AnalyzeResult,
  Clarification,
  HallElement,
  HallElementType,
  HallGuest,
  HallState,
  TableShape,
} from '../types'
import { SIDE_LABELS } from '../types'

interface TableView {
  table_number: number
  x: number
  y: number
  guests: HallGuest[]
  shape: TableShape
  rotation: number
}

const TABLE_W = 172

const REL_TEXT: Record<Clarification['relation_type'], string> = {
  avoid: 'לא לשבת עם',
  together: 'לשבת עם',
}

// הגדרות ברירת-מחדל לכל סוג אלמנט מיוחד (תווית + גודל).
const ELEMENT_DEFS: Record<
  HallElementType,
  { label: string; width: number; height: number }
> = {
  head_table: { label: 'שולחן מחותנים', width: 220, height: 56 },
  dance_floor: { label: 'רחבת ריקודים', width: 230, height: 200 },
  bar: { label: 'בר', width: 130, height: 90 },
  stage: { label: 'במה', width: 200, height: 74 },
  dj: { label: 'עמדת DJ', width: 110, height: 70 },
  entrance: { label: 'כניסה', width: 110, height: 40 },
  gift_table: { label: 'שולחן מתנות', width: 120, height: 46 },
  restroom: { label: 'שירותים', width: 90, height: 46 },
}

const ELEMENT_ORDER: HallElementType[] = [
  'head_table',
  'dance_floor',
  'bar',
  'stage',
  'dj',
  'gift_table',
  'restroom',
  'entrance',
]

export function HallPage() {
  const [tables, setTables] = useState<TableView[]>([])
  const [unassigned, setUnassigned] = useState<HallGuest[]>([])
  const [elements, setElements] = useState<HallElement[]>([])
  const [seats, setSeats] = useState(12)
  const [warnings, setWarnings] = useState<string[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [selectedEl, setSelectedEl] = useState<string | null>(null)
  const [selectedTable, setSelectedTable] = useState<number | null>(null)
  const [dragOver, setDragOver] = useState<number | 'tray' | null>(null)
  const [dirty, setDirty] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // סקיצת האולם (data URL) — רקע עדין מתחת לשולחנות.
  const [sketch, setSketch] = useState<string | null>(null)
  const sketchInputRef = useRef<HTMLInputElement | null>(null)

  // ---- אילוצים מההערות (לולאת הבהרות) ----
  const [clarifications, setClarifications] = useState<Clarification[]>([])
  const [analyzeSummary, setAnalyzeSummary] = useState<AnalyzeResult | null>(null)
  const [analyzing, setAnalyzing] = useState(false)

  // גרירת פריט (שולחן/אלמנט) או עריכת אלמנט (שינוי גודל/סיבוב) — pointer
  type DragState =
    | { kind: 'table'; id: number; dx: number; dy: number }
    | { kind: 'table-rotate'; id: number; cx: number; cy: number }
    | { kind: 'element'; id: string; dx: number; dy: number }
    | {
        kind: 'resize'
        id: string
        startX: number
        startY: number
        startW: number
        startH: number
      }
    | { kind: 'rotate'; id: string; cx: number; cy: number; startRot: number }
  const dragRef = useRef<DragState | null>(null)
  const canvasRef = useRef<HTMLDivElement | null>(null)

  const applyState = useCallback((h: HallState) => {
    setTables(
      h.tables.map((t) => ({
        table_number: t.table_number,
        x: t.x,
        y: t.y,
        guests: t.guests,
        shape: t.shape ?? 'round',
        rotation: t.rotation ?? 0,
      })),
    )
    setUnassigned(h.unassigned)
    setElements(h.elements ?? [])
    setSeats(h.seats_per_table)
    setWarnings(h.warnings)
    setSketch(h.sketch ?? null)
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

  const loadClarifications = useCallback(async () => {
    try {
      setClarifications(await listClarifications())
    } catch {
      /* שקט — לא חוסם את מפת האולם */
    }
  }, [])

  useEffect(() => {
    load()
    loadClarifications()
  }, [load, loadClarifications])

  async function onAnalyze() {
    setAnalyzing(true)
    setError('')
    try {
      setAnalyzeSummary(await analyzeConstraints())
      await loadClarifications()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בניתוח ההערות')
    } finally {
      setAnalyzing(false)
    }
  }

  async function onResolve(id: number, chosenGuestId: number | null) {
    try {
      setAnalyzeSummary(await resolveClarification(id, chosenGuestId))
      await loadClarifications()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בפתרון ההבהרה')
    }
  }

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

  function onTableRotatePointerDown(e: React.PointerEvent, tnum: number) {
    e.stopPropagation()
    const graphic = (e.currentTarget as HTMLElement).parentElement
    if (!graphic) return
    const r = graphic.getBoundingClientRect()
    dragRef.current = {
      kind: 'table-rotate',
      id: tnum,
      cx: r.left + r.width / 2,
      cy: r.top + r.height / 2,
    }
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
  }

  function setTableShape(tnum: number, shape: TableShape) {
    setTables((prev) =>
      prev.map((t) =>
        t.table_number === tnum
          ? { ...t, shape, rotation: shape === 'round' ? 0 : t.rotation }
          : t,
      ),
    )
    setDirty(true)
  }

  function onElementPointerDown(e: React.PointerEvent, id: string) {
    const el = elements.find((x) => x.id === id)
    if (!el || !canvasRef.current) return
    setSelectedEl(id)
    if (el.locked) return // נעול — לא זז
    const rect = canvasRef.current.getBoundingClientRect()
    dragRef.current = {
      kind: 'element',
      id,
      dx: e.clientX - rect.left - el.x,
      dy: e.clientY - rect.top - el.y,
    }
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
  }

  function onResizePointerDown(e: React.PointerEvent, id: string) {
    e.stopPropagation()
    const el = elements.find((x) => x.id === id)
    if (!el) return
    dragRef.current = {
      kind: 'resize',
      id,
      startX: e.clientX,
      startY: e.clientY,
      startW: el.width,
      startH: el.height,
    }
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
  }

  function onRotatePointerDown(e: React.PointerEvent, id: string) {
    e.stopPropagation()
    const el = elements.find((x) => x.id === id)
    if (!el || !canvasRef.current) return
    const rect = canvasRef.current.getBoundingClientRect()
    dragRef.current = {
      kind: 'rotate',
      id,
      cx: rect.left + el.x + el.width / 2,
      cy: rect.top + el.y + el.height / 2,
      startRot: el.rotation,
    }
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
  }

  function onCanvasPointerMove(e: React.PointerEvent) {
    const drag = dragRef.current
    if (!drag || !canvasRef.current) return
    const rect = canvasRef.current.getBoundingClientRect()

    if (drag.kind === 'table') {
      const x = Math.max(0, e.clientX - rect.left - drag.dx)
      const y = Math.max(0, e.clientY - rect.top - drag.dy)
      setTables((prev) =>
        prev.map((t) => (t.table_number === drag.id ? { ...t, x, y } : t)),
      )
    } else if (drag.kind === 'table-rotate') {
      const deg =
        (Math.atan2(e.clientY - drag.cy, e.clientX - drag.cx) * 180) / Math.PI +
        90
      setTables((prev) =>
        prev.map((t) =>
          t.table_number === drag.id ? { ...t, rotation: Math.round(deg) } : t,
        ),
      )
    } else if (drag.kind === 'element') {
      const x = Math.max(0, e.clientX - rect.left - drag.dx)
      const y = Math.max(0, e.clientY - rect.top - drag.dy)
      setElements((prev) =>
        prev.map((el) => (el.id === drag.id ? { ...el, x, y } : el)),
      )
    } else if (drag.kind === 'resize') {
      const w = Math.max(40, drag.startW + (e.clientX - drag.startX))
      const h = Math.max(30, drag.startH + (e.clientY - drag.startY))
      setElements((prev) =>
        prev.map((el) =>
          el.id === drag.id ? { ...el, width: w, height: h } : el,
        ),
      )
    } else if (drag.kind === 'rotate') {
      const deg =
        (Math.atan2(e.clientY - drag.cy, e.clientX - drag.cx) * 180) / Math.PI +
        90
      setElements((prev) =>
        prev.map((el) =>
          el.id === drag.id ? { ...el, rotation: Math.round(deg) } : el,
        ),
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
      rotation: 0,
      locked: false,
      label: def.label,
    }
    setElements((prev) => [...prev, el])
    setSelectedEl(el.id)
    setDirty(true)
  }

  function removeElement(id: string) {
    setElements((prev) => prev.filter((el) => el.id !== id))
    if (selectedEl === id) setSelectedEl(null)
    setDirty(true)
  }

  function toggleLock(id: string) {
    setElements((prev) =>
      prev.map((el) => (el.id === id ? { ...el, locked: !el.locked } : el)),
    )
    setDirty(true)
  }

  function duplicateElement(id: string) {
    setElements((prev) => {
      const src = prev.find((el) => el.id === id)
      if (!src) return prev
      const copy: HallElement = {
        ...src,
        id: `${src.type}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        x: src.x + 24,
        y: src.y + 24,
        locked: false,
      }
      setSelectedEl(copy.id)
      return [...prev, copy]
    })
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
    if (selected !== null) {
      moveGuestToTable(selected, tnum)
      return
    }
    setSelectedEl(null)
    setSelectedTable((cur) => (cur === tnum ? null : tnum))
  }

  function onTrayClick() {
    if (selected !== null) moveGuestToTable(selected, null)
  }

  // ---- גרירת מוזמן אמיתית (HTML5 drag & drop) ----
  function onGuestDragStart(e: React.DragEvent, guestId: number) {
    e.dataTransfer.setData('text/plain', String(guestId))
    e.dataTransfer.effectAllowed = 'move'
    setSelected(null)
  }

  function onDropTo(e: React.DragEvent, target: number | null) {
    e.preventDefault()
    const gid = Number(e.dataTransfer.getData('text/plain'))
    if (!Number.isNaN(gid)) moveGuestToTable(gid, target)
    setDragOver(null)
  }

  // ---- סקיצת האולם ----
  function onPickSketch(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = '' // מאפשר לבחור שוב את אותו קובץ
    if (!file) return
    if (!file.type.startsWith('image/')) {
      setError('יש לבחור קובץ תמונה (JPG/PNG).')
      return
    }
    if (file.size > 4 * 1024 * 1024) {
      setError('התמונה גדולה מדי (עד 4MB). נסו תמונה קטנה יותר.')
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      setSketch(typeof reader.result === 'string' ? reader.result : null)
      setDirty(true)
    }
    reader.readAsDataURL(file)
  }

  function removeSketch() {
    setSketch(null)
    setDirty(true)
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
        shape: t.shape,
        rotation: t.rotation,
      }))
      applyState(await saveHall(payload, seats, elements, sketch ?? ''))
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
        setError('השיבוץ האוטומטי לא הצליח לשמור על כל החוקים — כדאי לנסות עם יותר כיסאות לשולחן.')
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
      {/* ---- אילוצים מההערות (לפני השיבוץ) ---- */}
      <div className="clar-panel">
        <div className="clar-head">
          <div>
            <h3 className="clar-title">אילוצים מההערות</h3>
            <p className="clar-sub">
              המערכת קוראת את ההערות החופשיות והופכת אותן לכללי הושבה ("לא
              לשבת עם", "לשבת ליד") לפני יצירת השיבוץ.
            </p>
          </div>
          <button className="btn-ghost" onClick={onAnalyze} disabled={analyzing}>
            {analyzing ? 'מנתח…' : '↻ ניתוח הערות'}
          </button>
        </div>

        {analyzeSummary && (
          <p className="clar-summary">
            נותחו {analyzeSummary.guests_analyzed} מוזמנים ·{' '}
            {analyzeSummary.resolved} אילוצים זוהו ·{' '}
            {analyzeSummary.pending_clarifications} ממתינים להבהרה
          </p>
        )}

        {clarifications.length > 0 ? (
          <div className="clar-list">
            {clarifications.map((c) => (
              <div className="clar-card" key={c.id}>
                <div className="clar-q">
                  <strong>{c.source_guest_name}</strong> ביקש/ה{' '}
                  {REL_TEXT[c.relation_type]} "<strong>{c.target_text}</strong>" —
                  למי הכוונה?
                </div>
                <div className="clar-actions">
                  {c.candidates.map((cand) => (
                    <button
                      key={cand.id}
                      className="btn-ghost clar-choice"
                      onClick={() => onResolve(c.id, cand.id)}
                    >
                      {cand.full_name}
                    </button>
                  ))}
                  <button
                    className="btn-text"
                    onClick={() => onResolve(c.id, null)}
                  >
                    אף אחד מהם
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          analyzeSummary && <p className="clar-ok">אין הבהרות ממתינות ✓</p>
        )}
      </div>

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
          {loading ? 'שומר…' : dirty ? 'שמירת המפה' : 'נשמר ✓'}
        </button>
        <input
          ref={sketchInputRef}
          type="file"
          accept="image/*"
          hidden
          onChange={onPickSketch}
        />
        <button
          className="btn-ghost"
          onClick={() => sketchInputRef.current?.click()}
        >
          {sketch ? '🖼 החלפת סקיצה' : '🖼 העלאת סקיצת אולם'}
        </button>
        {sketch && (
          <button className="btn-text" onClick={removeSketch}>
            הסרת סקיצה
          </button>
        )}
        <span className="hall-hint">
          גררו שולחן להזזה · לחצו שולחן לבחירה (עגול/ארוך + סיבוב) · גררו מוזמן
          לשולחן
        </span>
      </div>

      <div className="hall-palette">
        <span className="palette-label">הוספה למפה:</span>
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
          className={`hall-tray ${selected !== null ? 'droppable' : ''} ${
            dragOver === 'tray' ? 'drag-over' : ''
          }`}
          onClick={onTrayClick}
          onDragOver={(e) => {
            e.preventDefault()
            setDragOver('tray')
          }}
          onDragLeave={() => setDragOver((c) => (c === 'tray' ? null : c))}
          onDrop={(e) => onDropTo(e, null)}
        >
          <h4 className="tray-title">ללא שולחן ({unassigned.length})</h4>
          {unassigned.length === 0 && <p className="tray-empty">כולם משובצים ✓</p>}
          {unassigned.map((g) => (
            <GuestChip
              key={g.id}
              g={g}
              selected={selected === g.id}
              onClick={(e) => onGuestClick(e, g.id)}
              onDragStart={(e) => onGuestDragStart(e, g.id)}
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
          onPointerDown={(e) => {
            if (e.target === e.currentTarget) {
              setSelectedEl(null)
              setSelectedTable(null)
            }
          }}
        >
          {sketch && (
            <div
              className="hall-sketch-bg"
              style={{ backgroundImage: `url(${sketch})` }}
              aria-hidden="true"
            />
          )}
          {tables.length === 0 && elements.length === 0 && (
            <p className="hall-empty">
              אין עדיין שולחנות. לחצו "שיבוץ אוטומטי מחדש" כדי לחלק את המוזמנים.
            </p>
          )}
          {elements.map((el) => {
            const isSel = selectedEl === el.id
            return (
              <div
                key={el.id}
                className={`hall-element el-${el.type} ${
                  isSel ? 'selected' : ''
                } ${el.locked ? 'locked' : ''}`}
                style={{
                  left: el.x,
                  top: el.y,
                  width: el.width,
                  height: el.height,
                  transform: `rotate(${el.rotation}deg)`,
                }}
                onPointerDown={(e) => onElementPointerDown(e, el.id)}
              >
                <span className="element-label">{el.label}</span>
                {el.locked && (
                  <span className="element-lock-badge" title="נעול">
                    🔒
                  </span>
                )}

                {isSel && (
                  <>
                    {/* סרגל עריכה צף */}
                    <div
                      className="element-toolbar"
                      onPointerDown={(e) => e.stopPropagation()}
                    >
                      <button
                        type="button"
                        title={el.locked ? 'שחרר נעילה' : 'נעל'}
                        onClick={(e) => {
                          e.stopPropagation()
                          toggleLock(el.id)
                        }}
                      >
                        {el.locked ? '🔓' : '🔒'}
                      </button>
                      <button
                        type="button"
                        title="שכפל"
                        onClick={(e) => {
                          e.stopPropagation()
                          duplicateElement(el.id)
                        }}
                      >
                        ⧉
                      </button>
                      <button
                        type="button"
                        title="מחק"
                        onClick={(e) => {
                          e.stopPropagation()
                          removeElement(el.id)
                        }}
                      >
                        ×
                      </button>
                    </div>

                    {!el.locked && (
                      <>
                        {/* ידית סיבוב */}
                        <span
                          className="handle handle-rotate"
                          title="סובב"
                          onPointerDown={(e) => onRotatePointerDown(e, el.id)}
                        />
                        {/* ידית שינוי גודל */}
                        <span
                          className="handle handle-resize"
                          title="שנה גודל"
                          onPointerDown={(e) => onResizePointerDown(e, el.id)}
                        />
                      </>
                    )}
                  </>
                )}
              </div>
            )
          })}
          {tables.map((t) => {
            const used = t.guests.reduce((s, g) => s + g.seats, 0)
            const over = used > seats
            const free = seats - used
            const isSelT = selectedTable === t.table_number
            return (
              <div
                key={t.table_number}
                className={`hall-table shape-${t.shape} ${over ? 'over' : ''} ${
                  selected !== null ? 'droppable' : ''
                } ${isSelT ? 'selected' : ''} ${
                  dragOver === t.table_number ? 'drag-over' : ''
                }`}
                style={{ left: t.x, top: t.y, width: TABLE_W }}
                onClick={() => onTableClick(t.table_number)}
                onDragOver={(e) => {
                  e.preventDefault()
                  setDragOver(t.table_number)
                }}
                onDragLeave={() =>
                  setDragOver((c) => (c === t.table_number ? null : c))
                }
                onDrop={(e) => onDropTo(e, t.table_number)}
              >
                <div
                  className={`table-graphic table-${t.shape}`}
                  style={{ transform: `rotate(${t.rotation}deg)` }}
                  onPointerDown={(e) => onTablePointerDown(e, t.table_number)}
                >
                  {t.shape === 'round' ? (
                    <SeatRing seats={seats} guests={t.guests} />
                  ) : (
                    <LongSeats seats={seats} guests={t.guests} />
                  )}
                  <span className="table-center">
                    <span className="table-num">{t.table_number}</span>
                    <span className="table-occ">
                      {used}/{seats}
                    </span>
                  </span>
                  {isSelT && t.shape === 'long' && (
                    <span
                      className="handle handle-rotate table-rot"
                      title="סובב שולחן"
                      onPointerDown={(e) => onTableRotatePointerDown(e, t.table_number)}
                    />
                  )}
                </div>

                {isSelT && (
                  <div
                    className="table-toolbar"
                    onClick={(e) => e.stopPropagation()}
                    onPointerDown={(e) => e.stopPropagation()}
                  >
                    <button
                      type="button"
                      className={t.shape === 'round' ? 'active' : ''}
                      onClick={() => setTableShape(t.table_number, 'round')}
                    >
                      ● עגול
                    </button>
                    <button
                      type="button"
                      className={t.shape === 'long' ? 'active' : ''}
                      onClick={() => setTableShape(t.table_number, 'long')}
                    >
                      ▬ ארוך
                    </button>
                  </div>
                )}

                {dragOver === t.table_number && (
                  <span className={`free-badge ${free <= 0 ? 'full' : ''}`}>
                    {free > 0 ? `${free} כיסאות פנויים` : 'השולחן מלא'}
                  </span>
                )}
                <div className="hall-table-body">
                  {t.guests.map((g) => (
                    <GuestChip
                      key={g.id}
                      g={g}
                      selected={selected === g.id}
                      onClick={(e) => onGuestClick(e, g.id)}
                      onDragStart={(e) => onGuestDragStart(e, g.id)}
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
  // הרחבת החבורות לכיסאות בודדים (לפי הכמות שאושרה בפועל), לצביעה לפי צד.
  const occupied: string[] = []
  for (const g of guests) {
    for (let i = 0; i < g.seats; i++) occupied.push(g.side)
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

// שולחן ארוך: כיסאות בשתי שורות (מעל ומתחת), צבועים לפי צד.
function LongSeats({ seats, guests }: { seats: number; guests: HallGuest[] }) {
  const occupied: string[] = []
  for (const g of guests) {
    for (let i = 0; i < g.seats; i++) occupied.push(g.side)
  }
  const count = Math.max(seats, occupied.length, 2)
  const top = Math.ceil(count / 2)
  const rows: number[][] = [
    Array.from({ length: top }, (_, i) => i),
    Array.from({ length: count - top }, (_, i) => top + i),
  ]
  return (
    <span className="long-seats" aria-hidden="true">
      {rows.map((row, r) => (
        <span key={r} className={`long-row ${r === 0 ? 'row-top' : 'row-bottom'}`}>
          {row.map((gi) => {
            const side = occupied[gi]
            return (
              <span
                key={gi}
                className={`seat-pip ${side ? `seat-${side}` : 'seat-free'} ${
                  gi >= seats ? 'seat-extra' : ''
                }`}
              />
            )
          })}
        </span>
      ))}
    </span>
  )
}

function GuestChip({
  g,
  selected,
  onClick,
  onDragStart,
}: {
  g: HallGuest
  selected: boolean
  onClick: (e: React.MouseEvent) => void
  onDragStart?: (e: React.DragEvent) => void
}) {
  return (
    <span
      className={`guest-chip side-${g.side} ${selected ? 'selected' : ''}`}
      draggable={!!onDragStart}
      onDragStart={onDragStart}
      onClick={onClick}
      title={`${SIDE_LABELS[g.side]} · גררו לשולחן או לחצו לבחירה`}
    >
      {g.full_name}
      {g.seats > 1 && <span className="chip-size">×{g.seats}</span>}
    </span>
  )
}
