import { matchAction, requestPattern, screenPattern, type RefKind } from './usagePatterns'

/**
 * Local usage log: route changes, key actions, slow waits and idle gaps, so a real batch can be
 * measured (Settings → Data → Usage log, `make usage-report`). Route patterns, action names and
 * ids only: no page content, no query text. Sent to the local API and stored in the local DB.
 */

interface UsageEvent {
  kind: 'screen' | 'action' | 'wait' | 'idle'
  name: string
  at: string
  screen?: string
  ref_kind?: RefKind
  ref_id?: number
  duration_ms?: number
  wall_ms?: number
}

const IDLE_MS = 5 * 60_000 // no input for this long is an idle gap and stops the active clock
const SLOW_MS = 500 // a request slower than this counts as waiting
const LOAD_WINDOW_MS = 3_000 // a GET this soon after a route change is the screen loading
const FLUSH_MS = 10_000
const MAX_BUFFER = 500

interface Current {
  name: string
  jobId: number | null
  enteredAt: number
  active: number
}

let enabled = true
let demo = false
let started = false
let current: Current | null = null
let lastInput = Date.now()
let lastTick = Date.now()
let lastNav = 0
let buffer: UsageEvent[] = []

const iso = (ms: number) => new Date(ms).toISOString()

function push(ev: UsageEvent) {
  if (!enabled || demo) return
  buffer.push(ev)
  if (buffer.length > MAX_BUFFER) buffer = buffer.slice(-MAX_BUFFER)
}

function closeScreen(now: number) {
  if (!current) return
  push({
    kind: 'screen',
    name: current.name,
    at: iso(current.enteredAt),
    ref_kind: current.jobId ? 'job' : undefined,
    ref_id: current.jobId ?? undefined,
    duration_ms: Math.round(current.active),
    wall_ms: now - current.enteredAt,
  })
}

async function flush(useBeacon = false) {
  if (!buffer.length || !enabled) return
  const events = buffer
  buffer = []
  const body = JSON.stringify({ events })
  try {
    if (useBeacon && navigator.sendBeacon?.('/api/usage/events', new Blob([body], { type: 'application/json' }))) return
    const res = await fetch('/api/usage/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      keepalive: true,
    })
    if (res.ok && (await res.json()).enabled === false) {
      enabled = false
      buffer = []
    }
  } catch {
    // The log is best effort: a failed flush just drops this batch.
  }
}

function onInput() {
  const now = Date.now()
  if (now - lastInput >= IDLE_MS) {
    push({ kind: 'idle', name: 'idle', at: iso(lastInput), duration_ms: now - lastInput })
  }
  lastInput = now
}

function tick() {
  const now = Date.now()
  const delta = Math.min(now - lastTick, 2_000)
  lastTick = now
  if (current && document.visibilityState === 'visible' && now - lastInput < IDLE_MS) current.active += delta
}

export function startUsageTracking() {
  if (started) return
  started = true
  for (const type of ['pointerdown', 'pointermove', 'keydown', 'wheel'])
    window.addEventListener(type, onInput, { passive: true, capture: true })
  window.setInterval(tick, 1_000)
  window.setInterval(() => void flush(), FLUSH_MS)
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') void flush(true)
  })
  window.addEventListener('pagehide', () => {
    closeScreen(Date.now())
    current = null
    void flush(true)
  })
}

export function trackScreen(pathname: string, search: string) {
  const now = Date.now()
  const next = screenPattern(pathname, search)
  if (current && current.name === next.name && current.jobId === next.jobId) return
  closeScreen(now)
  current = { name: next.name, jobId: next.jobId, enteredAt: now, active: 0 }
  lastNav = now
}

export function trackAction(name: string, ref?: { kind: RefKind; id: number } | null) {
  push({
    kind: 'action',
    name,
    at: iso(Date.now()),
    screen: current?.name,
    ref_kind: ref?.kind ?? (current?.jobId ? 'job' : undefined),
    ref_id: ref?.id ?? current?.jobId ?? undefined,
  })
}

/** Called by the API client for every request (the usage endpoints themselves are skipped). */
export function trackRequest(method: string, path: string, ms: number, ok: boolean) {
  if (path.startsWith('/usage')) return
  const now = Date.now()
  if (ok && method !== 'GET') {
    const action = matchAction(method, path)
    if (action) trackAction(action.name, action.ref)
  }
  if (ms >= SLOW_MS && (method !== 'GET' || now - lastNav < LOAD_WINDOW_MS + ms)) {
    push({
      kind: 'wait',
      name: `${method === 'GET' ? 'load' : method} ${requestPattern(path)}`.slice(0, 100),
      at: iso(now - ms),
      screen: current?.name,
      ref_kind: current?.jobId ? 'job' : undefined,
      ref_id: current?.jobId ?? undefined,
      duration_ms: Math.round(ms),
    })
  }
}

/** The tour sandbox never logs. */
export function setUsageDemo(on: boolean) {
  demo = on
}

/** The Settings switch (the server also refuses events while it is off). */
export function setUsageEnabled(on: boolean) {
  enabled = on
  if (!on) buffer = []
}
