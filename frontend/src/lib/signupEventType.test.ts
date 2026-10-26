/**
 * בדיקות להעברת סוג האירוע מדף הבית להרשמה (signupEventType.ts) — סקריפט
 * assert-פשוט, בלי framework, כמו hallSketchGeometry.test.ts.
 *
 * הרצה: npm run test:signup-event-type (ראה package.json)
 */
import {
  captureSignupEventType,
  clearSignupEventType,
  parseEventType,
  readSignupEventType,
} from './signupEventType'

function assert(cond: boolean, msg: string): void {
  if (!cond) throw new Error(`✗ ${msg}`)
}

function memStore() {
  const m = new Map<string, string>()
  return {
    getItem: (k: string) => (m.has(k) ? m.get(k)! : null),
    setItem: (k: string, v: string) => void m.set(k, v),
    removeItem: (k: string) => void m.delete(k),
    size: () => m.size,
  }
}

function testParse() {
  for (const t of ['wedding', 'henna', 'bar_mitzvah', 'bat_mitzvah', 'brit', 'brita', 'business']) {
    assert(parseEventType(t) === t, `parse accepts ${t}`)
  }
  for (const bad of ['', 'Wedding', 'party', 'toString', '__proto__', 'bar_mitzvah ', null, undefined]) {
    assert(parseEventType(bad) === null, `parse rejects ${String(bad)}`)
  }
}

function testRoundTrip() {
  const s = memStore()
  captureSignupEventType('?auth=register&event_type=bar_mitzvah', s)
  assert(readSignupEventType(s) === 'bar_mitzvah', 'captured value is read back')
  clearSignupEventType(s)
  assert(readSignupEventType(s) === null, 'cleared after first event')
}

function testIgnoresInvalidAndMissing() {
  const s = memStore()
  captureSignupEventType('?auth=register', s)
  assert(s.size() === 0, 'nothing stored without event_type')
  captureSignupEventType('?auth=register&event_type=<script>', s)
  assert(s.size() === 0, 'invalid value is not stored')
  // ערך תקין קודם לא נדרס על ידי ערך לא תקין
  captureSignupEventType('?event_type=henna', s)
  captureSignupEventType('?event_type=nope', s)
  assert(readSignupEventType(s) === 'henna', 'invalid value does not overwrite a valid one')
}

function testTamperedStorage() {
  const s = memStore()
  s.setItem('veya.signupEventType', 'evil')
  assert(readSignupEventType(s) === null, 'tampered storage value is ignored')
}

function testNoStorage() {
  captureSignupEventType('?event_type=brit', null)
  assert(readSignupEventType(null) === null, 'no storage → no preselect, no crash')
  clearSignupEventType(null)
}

testParse()
testRoundTrip()
testIgnoresInvalidAndMissing()
testTamperedStorage()
testNoStorage()
console.log('✓ signupEventType: all tests passed')
