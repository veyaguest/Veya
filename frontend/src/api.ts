import type {
  Guest,
  GuestCreate,
  ImportPreview,
  SeatingRequest,
  SeatingResult,
} from './types'

const API_URL = 'http://localhost:8000'

/** מחלץ הודעת שגיאה קריאה מתשובת FastAPI (כולל שגיאות ולידציה 422). */
async function toError(res: Response): Promise<Error> {
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') return new Error(body.detail)
    if (Array.isArray(body.detail)) {
      const msgs = body.detail.map((d: { msg: string }) => d.msg).join(', ')
      return new Error(msgs || `שגיאה ${res.status}`)
    }
  } catch {
    /* ignore */
  }
  return new Error(`שגיאה ${res.status}`)
}

export async function healthCheck(): Promise<boolean> {
  try {
    const res = await fetch(`${API_URL}/health`)
    return res.ok
  } catch {
    return false
  }
}

export async function listGuests(q?: string): Promise<Guest[]> {
  const url = new URL(`${API_URL}/guests`)
  if (q) url.searchParams.set('q', q)
  const res = await fetch(url)
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function createGuest(data: GuestCreate): Promise<Guest> {
  const res = await fetch(`${API_URL}/guests`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function deleteGuest(id: number): Promise<void> {
  const res = await fetch(`${API_URL}/guests/${id}`, { method: 'DELETE' })
  if (!res.ok) throw await toError(res)
}

export async function previewImport(file: File): Promise<ImportPreview> {
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetch(`${API_URL}/guests/import/preview`, {
    method: 'POST',
    body: fd,
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function commitImport(
  rows: GuestCreate[],
): Promise<{ created: number }> {
  const res = await fetch(`${API_URL}/guests/import/commit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rows }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function generateSeating(
  req: SeatingRequest,
): Promise<SeatingResult> {
  const res = await fetch(`${API_URL}/seating/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}
