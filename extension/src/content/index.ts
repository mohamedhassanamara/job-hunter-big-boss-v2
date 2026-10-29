/**
 * The floating control. It reads the page ONLY inside a click (or the keyboard shortcut / popup request),
 * never on a timer or by observing the page, and never clicks, scrolls or requests anything from LinkedIn.
 * A save sends what it read to YOUR app on this computer (through the worker, which holds the token).
 */
import { extract, type Extraction } from '../shared/extract'
import { buildReport } from '../shared/report'
import { skeleton } from '../shared/structure'
import { pageOf, type PageKind } from '../shared/urls'

const EXT_VERSION = '0.1.0'

type Child = Node | string | null | false
function h<K extends keyof HTMLElementTagNameMap>(tag: K, props: Record<string, string> = {}, ...kids: Child[]): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag)
  for (const [k, v] of Object.entries(props)) el.setAttribute(k, v)
  for (const kid of kids) if (kid) el.append(kid)
  return el
}

const STYLE = `
  :host { all: initial }
  * { box-sizing: border-box; font: 13px/1.4 system-ui, sans-serif; color: CanvasText }
  .wrap { position: fixed; right: 16px; bottom: 16px; z-index: 2147483646; display: flex; flex-direction: column; align-items: flex-end; gap: 8px }
  .pill { border: 1px solid GrayText; background: Canvas; border-radius: 999px; padding: 8px 14px; cursor: pointer; box-shadow: 0 2px 10px rgb(0 0 0 / 25%) }
  .dot { width: 14px; height: 14px; padding: 0 }
  .panel { width: 360px; max-height: 75vh; overflow: auto; border: 1px solid GrayText; background: Canvas; border-radius: 10px; padding: 12px; box-shadow: 0 2px 14px rgb(0 0 0 / 30%); display: flex; flex-direction: column; gap: 8px }
  .row { display: flex; gap: 6px; align-items: baseline } .ok { color: #1a7f37 } .no { color: #cf222e }
  .small { font-size: 12px; color: GrayText } .btns { display: flex; gap: 6px; flex-wrap: wrap }
  .warn { font-size: 12px; color: #9a6700 } h3 { font-weight: 600; margin: 0 }
  button { cursor: pointer; border: 1px solid GrayText; background: Canvas; border-radius: 6px; padding: 4px 8px }
  button.primary { background: Highlight; color: HighlightText; border-color: Highlight } button.primary * { color: HighlightText }
  button[aria-pressed="true"] { background: Highlight; color: HighlightText; border-color: Highlight }
  input[type="text"], textarea { width: 100%; border: 1px solid GrayText; border-radius: 6px; padding: 4px 6px; background: Canvas }
  textarea { min-height: 70px } a { color: LinkText } summary { cursor: pointer }
`

interface ApiResult {
  ok: boolean
  status: number
  data: unknown
  error?: string
}
interface JobOut {
  saved: boolean
  missing: string[]
  warnings: string[]
  job_id: number | null
  created: boolean
  duplicate_of: { title?: string } | null
  scoring: string
  parsed: Record<string, string>
}
interface PersonOut {
  saved: boolean
  missing: string[]
  warnings: string[]
  name: string
  headline: string
  location: string
  current_title: string
  current_company: string
  degree: number | null
  persona: string
  persona_reasons: string[]
  persona_source: string
  alumni: boolean
  school: string | null
  job: { job_id: number; title: string; stage: string } | null
  existing: boolean
  contact_id: number | null
  do_not_contact: string | null
}

const root = h('div')
const shadow = root.attachShadow({ mode: 'closed' })
let open = false
let collapsed = false
let busy = ''
let last: Extraction | null = null
let includeText = false
let note = ''
let appUrl = 'http://localhost:5173'
let paired = true
// what the panel is showing
let jobResult: JobOut | null = null
let jobTyped: Record<string, string> = {}
let person: PersonOut | null = null
let personChoice: { persona: string | null; alumni: boolean | null; company: string; detach: boolean; paste: string } = { persona: null, alumni: null, company: '', detach: false, paste: '' }
let personSaved = false
let showPaste = false
let message = ''

const kindLabel = (k: PageKind): string => (k === 'job' ? 'Save job' : k === 'profile' ? 'Save person' : 'Open a job or profile')
const here = (): PageKind => pageOf(location.href).kind
let pillEl: HTMLButtonElement | null = null
/** LinkedIn changes the URL without a reload; the label follows the live URL, never a cached one. */
const refreshLabel = (): void => {
  if (pillEl) pillEl.textContent = busy ? 'Working…' : kindLabel(here())
}

async function api(path: string, method: 'GET' | 'POST' | 'PATCH', body?: unknown): Promise<ApiResult> {
  return (await chrome.runtime.sendMessage({ type: 'api', path, method, body })) as ApiResult
}

/** One sentence for each way an app call can fail. */
function failure(r: ApiResult): string {
  if (r.error === 'no-token') return 'Not paired yet: open the extension options and paste your token.'
  if (r.status === 401) return 'The app refused the token: create a new one in Settings → LinkedIn.'
  if (r.status === 0) return r.error === 'unreachable' ? 'Could not reach the app: is it running (make dev)?' : (r.error ?? 'Could not call the app')
  const d = r.data as { detail?: unknown } | null
  return typeof d?.detail === 'string' ? d.detail : `The app answered ${r.status}`
}

async function copy(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    const ta = h('textarea')
    ta.value = text
    shadow.append(ta)
    ta.select()
    const ok = document.execCommand('copy')
    ta.remove()
    return ok
  }
}

function reset(): void {
  jobResult = null
  jobTyped = {}
  person = null
  personSaved = false
  showPaste = false
  message = ''
  personChoice = { persona: null, alumni: null, company: '', detach: false, paste: '' }
}

async function start(): Promise<void> {
  const kind = here()
  open = true
  collapsed = false
  reset()
  const cfg = (await chrome.runtime.sendMessage({ type: 'config' })) as { app: string; paired: boolean }
  appUrl = cfg.app
  paired = cfg.paired
  last = extract(document, location)
  if (kind === 'other') message = 'This is not a job or a profile page. Open one, then press again.'
  else if (!paired) message = 'Not paired yet: open the extension options and paste your token.'
  else if (kind === 'job') await saveJob()
  else await previewPerson()
  render()
}

async function saveJob(): Promise<void> {
  busy = 'Saving the job…'
  render()
  const x = extract(document, location, true)
  last = extract(document, location)
  const r = await api('/ext/job', 'POST', { payload: x.payload, fields: jobTyped })
  busy = ''
  if (r.ok) jobResult = r.data as JobOut
  else message = failure(r)
}

function personBody(extra: Record<string, unknown> = {}): Record<string, unknown> {
  const c = personChoice
  const x = c.paste ? null : extract(document, location, true)
  return {
    payload: x?.payload ?? null,
    paste: c.paste || null,
    url: location.href.split('?')[0],
    company: c.company || null,
    persona: c.persona,
    alumni: c.alumni,
    job_id: c.detach ? 0 : null,
    extension_version: EXT_VERSION,
    ...extra,
  }
}

async function previewPerson(): Promise<void> {
  busy = 'Reading the profile…'
  render()
  last = extract(document, location)
  const r = await api('/ext/person/preview', 'POST', personBody())
  busy = ''
  if (r.ok) {
    person = r.data as PersonOut
    personChoice.company = personChoice.company || person.current_company
  } else message = failure(r)
}

async function savePerson(): Promise<void> {
  busy = 'Saving…'
  render()
  // Only what you changed is sent: an auto-detected role stays auto (a recapture can improve it).
  const r = await api('/ext/person', 'POST', personBody())
  busy = ''
  if (r.ok) {
    const out = r.data as PersonOut
    if (out.saved) {
      person = out
      personSaved = true
    } else message = `Still missing: ${out.missing.join(', ')}`
  } else message = failure(r)
}

// ----------------------------------------------------------------------------- rendering

function button(label: string, onClick: () => void, cls = ''): HTMLButtonElement {
  const b = h('button', { type: 'button', ...(cls ? { class: cls } : {}) }, label)
  b.addEventListener('click', onClick)
  return b
}

const redo = (fn: () => Promise<void>) => () => void fn().then(render)

function jobView(): Node[] {
  const out: Node[] = []
  if (jobResult?.saved) {
    const r = jobResult
    out.push(h('h3', {}, `Saved · ${r.parsed.title} @ ${r.parsed.company}`))
    const facts = [r.parsed.location, r.parsed.workplace].filter(Boolean).join(' · ')
    if (facts) out.push(h('div', { class: 'small' }, facts))
    out.push(h('div', { class: 'small' }, r.duplicate_of ? 'Merged into a listing you already had.' : r.created ? 'New job.' : 'Updated.'))
    out.push(h('div', { class: 'small' }, r.scoring === 'queued' ? 'Scoring now.' : `Scoring: ${r.scoring}`))
    for (const w of r.warnings) out.push(h('div', { class: 'warn' }, w))
    if (r.job_id) out.push(h('a', { href: `${appUrl}/jobs/${r.job_id}`, target: '_blank', rel: 'noreferrer' }, 'Open in the app'))
  } else if (jobResult && jobResult.missing.length) {
    const r = jobResult
    out.push(h('h3', {}, 'Nothing saved yet: fill in what the page did not give'))
    for (const field of r.missing) {
      const input = field === 'description' ? h('textarea', { 'aria-label': field }) : h('input', { type: 'text', 'aria-label': field })
      input.value = jobTyped[field] ?? r.parsed[field] ?? ''
      input.addEventListener('input', () => {
        jobTyped[field] = input.value
      })
      out.push(h('div', { class: 'small' }, field), input)
    }
    for (const w of r.warnings) out.push(h('div', { class: 'warn' }, w))
    out.push(h('div', { class: 'btns' }, button('Save', redo(saveJob), 'primary')))
  }
  return out
}

function personView(): Node[] {
  const out: Node[] = []
  if (!person) return out
  const p = person
  out.push(h('h3', {}, personSaved ? `Saved · ${p.name}` : p.name || 'Unknown name'))
  const line = [p.current_title || p.headline, p.current_company].filter(Boolean).join(' @ ')
  if (line) out.push(h('div', { class: 'small' }, line))
  if (p.location) out.push(h('div', { class: 'small' }, p.location))
  if (p.do_not_contact) out.push(h('div', { class: 'warn' }, p.do_not_contact))
  const chosen = personChoice.persona ?? p.persona
  const chips = h('div', { class: 'btns' })
  for (const [value, label] of [['recruiter', 'Recruiter'], ['lead', 'Team lead'], ['peer', 'Peer']] as const) {
    const b = h('button', { type: 'button', 'aria-pressed': String(chosen === value) }, label)
    b.addEventListener('click', () => {
      personChoice.persona = value
      render()
    })
    chips.append(b)
  }
  out.push(h('div', { class: 'small' }, 'Role'), chips)
  const why = personChoice.persona ? 'Set by you.' : p.persona_reasons.join('; ')
  if (why) out.push(h('div', { class: 'small' }, why))
  const alum = h('input', { type: 'checkbox' })
  alum.checked = personChoice.alumni ?? p.alumni
  alum.addEventListener('change', () => {
    personChoice.alumni = alum.checked
  })
  out.push(h('label', { class: 'row' }, alum, `${p.school ?? 'School'} alum`))
  if (!personSaved) {
    const company = h('input', { type: 'text', 'aria-label': 'Company' })
    company.value = personChoice.company
    company.addEventListener('change', () => {
      personChoice.company = company.value.trim()
      void previewPerson().then(render)
    })
    out.push(h('div', { class: 'small' }, p.missing.includes('company') ? 'Company (the page did not give it)' : 'Company'), company)
  }
  if (p.job) {
    out.push(h('div', { class: 'small' }, `Joins: ${p.job.title} (${p.job.stage})`))
    if (!personSaved) {
      const keep = h('input', { type: 'checkbox' })
      keep.checked = personChoice.detach
      keep.addEventListener('change', () => {
        personChoice.detach = keep.checked
      })
      out.push(h('label', { class: 'row' }, keep, 'Keep as a contact only'))
    }
  } else {
    out.push(h('div', { class: 'small' }, 'No open job at this company: saved as a contact, joins the next job you capture there.'))
  }
  for (const w of p.warnings) out.push(h('div', { class: 'warn' }, w))
  if (personSaved) {
        out.push(h('a', { href: `${appUrl}/linkedin`, target: '_blank', rel: 'noreferrer' }, 'Open in the app'))
  }
  out.push(h('div', { class: 'btns' }, button(personSaved ? 'Save again' : 'Save person', redo(savePerson), 'primary')))
  return out
}

function pasteView(): Node[] {
  if (!showPaste) {
    return [
      button('Paste profile text instead', () => {
        showPaste = true
        render()
      }),
    ]
  }
  const ta = h('textarea', { 'aria-label': 'Profile text', placeholder: 'Paste the profile header (name, headline, company)…' })
  ta.value = personChoice.paste
  return [
    ta,
    button(
      'Use pasted text',
      redo(async () => {
        personChoice.paste = ta.value
        message = ''
        await previewPerson()
      }),
    ),
  ]
}

function details(): Node {
  const rows = (last?.anchors ?? []).map((a) => h('div', { class: 'row' }, h('span', { class: a.ok ? 'ok' : 'no' }, a.ok ? '✓' : '✗'), h('span', {}, a.name + (a.note ? ` (${a.note})` : ''))))
  const box = h('input', { type: 'checkbox' })
  box.checked = includeText
  box.addEventListener('change', () => {
    includeText = box.checked
    void chrome.storage.local.set({ includeText })
  })
  const mk = (label: string, fn: () => string) =>
    button(label, () => {
      void copy(fn()).then((ok) => {
        note = ok ? `${label}: copied` : `${label}: copy failed`
        render()
      })
    })
  return h(
    'details',
    {},
    h('summary', { class: 'small' }, 'Details (what was read)'),
    ...rows,
    h('div', { class: 'btns' }, mk('Copy report', () => buildReport(extract(document, location), includeText)), mk('Copy page structure', () => skeleton(document, includeText))),
    h('label', { class: 'small' }, box, ' Include page text (only on your own pages)'),
    h('div', { class: 'small' }, note || 'Reports are redacted unless you tick the box.'),
  )
}

function render(): void {
  const kind = here()
  const style = h('style')
  style.textContent = STYLE
  const wrap = h('div', { class: 'wrap' })
  if (open) {
    const panel = h('div', { class: 'panel' })
    if (busy) panel.append(h('div', {}, busy))
    else {
      if (message) {
        panel.append(h('div', { class: 'warn' }, message))
        if (!paired || message.startsWith('The app refused')) panel.append(button('Open extension options', () => void chrome.runtime.sendMessage({ type: 'options' })))
      }
      if (kind === 'job') panel.append(...jobView())
      if (kind === 'profile') {
        panel.append(...personView())
        if (!person || message) panel.append(...pasteView())
      }
      panel.append(details())
    }
    panel.append(
      h(
        'div',
        { class: 'btns' },
        button('Close', () => {
          open = false
          render()
        }),
      ),
    )
    wrap.append(panel)
  }
  if (collapsed) {
    wrap.append(
      button(
        '',
        () => {
          collapsed = false
          render()
        },
        'pill dot',
      ),
    )
  } else {
    const pill = h('button', { type: 'button', class: 'pill' }, busy ? 'Working…' : kindLabel(kind))
    pillEl = pill
    pill.addEventListener('pointerenter', refreshLabel)
    pill.addEventListener('focus', refreshLabel)
    pill.addEventListener('click', () => void start())
    wrap.append(
      h(
        'div',
        { class: 'row' },
        pill,
        button('–', () => {
          collapsed = true
          open = false
          render()
        }),
      ),
    )
  }
  shadow.replaceChildren(style, wrap)
}

chrome.runtime.onMessage.addListener((raw, _sender, send) => {
  const msg = raw as { type: string; includeText?: boolean }
  if (msg.type === 'url') {
    open = false
    last = null
    reset()
    render()
  } else if (msg.type === 'command') {
    void start()
  } else if (msg.type === 'info') {
    send({ page: here() })
  } else if (msg.type === 'check') {
    const x = extract(document, location)
    send({ page: x.page, anchors: x.anchors, report: buildReport(x, !!msg.includeText) })
  } else if (msg.type === 'structure') {
    send({ structure: skeleton(document, !!msg.includeText) })
  }
  return true
})

// Same-page navigations (no reload, no message from the worker): events only, nothing is polled.
window.addEventListener('popstate', refreshLabel)
;(window as unknown as { navigation?: EventTarget }).navigation?.addEventListener('currententrychange', refreshLabel)

void chrome.storage.local.get('includeText').then((v) => {
  includeText = v.includeText === true
})
document.documentElement.append(root)
render()
