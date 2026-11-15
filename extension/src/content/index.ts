/**
 * The floating control: ONE button, chosen by the page type ("Save job" on a job page, "Save profile" on a
 * profile). One click saves; there is no review screen. It reads the page ONLY inside that click (or the
 * keyboard shortcut), never on a timer or by observing the page, and never clicks, scrolls or requests
 * anything from LinkedIn. The save goes to YOUR app on this computer (through the worker, which holds the
 * token). Afterwards the panel shows what was saved and where each field came from, and the app's LinkedIn
 * Jobs / Profiles sections flag anything that looks misread.
 *
 * One more thing happens on a profile page without a click: a LOOKUP. It sends only the profile slug from
 * `location.pathname` (never the page) to your app on this computer, which answers whether you saved this
 * person and on which jobs, so the panel can offer "View jobs associated with profile". It only reads; it
 * saves nothing, drafts nothing and changes no status. If the app or the token is missing, nothing shows.
 */
import { extract, type Extraction } from '../shared/extract'
import { buildReport } from '../shared/report'
import { skeleton } from '../shared/structure'
import { jobPath, lookupPath, slugFromPath, statusLabel, viewOf, type LookupResult } from '../shared/lookup'
import { pageOf, type PageKind } from '../shared/urls'

const EXT_VERSION = '0.2.0'

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
  .pill.save { background: Highlight; border-color: Highlight; color: HighlightText; font-weight: 600 } .pill.save * { color: HighlightText }
  .pill.idle { opacity: .6; cursor: default }
  .dot { width: 14px; height: 14px; padding: 0 }
  a.pill { text-decoration: none; display: inline-block } a.pill.link, a.pill.link * { background: Highlight; border-color: Highlight; color: HighlightText; font-weight: 600 }
  .stack { display: flex; flex-direction: column; align-items: flex-end; gap: 8px }
  .jobs { display: flex; flex-direction: column; gap: 4px; border: 1px solid GrayText; background: Canvas; border-radius: 10px; padding: 8px 10px; box-shadow: 0 2px 14px rgb(0 0 0 / 30%); max-width: 360px }
  .panel { width: 360px; max-height: 75vh; overflow: auto; border: 1px solid GrayText; background: Canvas; border-radius: 10px; padding: 12px; box-shadow: 0 2px 14px rgb(0 0 0 / 30%); display: flex; flex-direction: column; gap: 6px }
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
interface Flag {
  code: string
  text: string
}
interface JobOut {
  saved: boolean
  missing: string[]
  warnings: string[]
  flags: Flag[]
  undo: boolean
  job_id: number | null
  created: boolean
  duplicate_of: { title?: string } | null
  scoring: string
  parsed: Record<string, string>
  sources: Record<string, string>
  description_chars: number
  description_level: string
}
interface PersonOut {
  saved: boolean
  missing: string[]
  warnings: string[]
  flags: Flag[]
  undo: boolean
  name: string
  headline: string
  location: string
  current_title: string
  current_company: string
  persona: string
  persona_reasons: string[]
  alumni: boolean
  school: string | null
  job: { job_id: number; title: string; stage: string } | null
  contact_id: number | null
  do_not_contact: string | null
  linked?: LookupResult | null
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
let companyTyped = ''
let paste = ''
let showPaste = false
let undone = ''
let message = ''
// the lookup: what the app says about the profile open in this tab (in memory, per tab)
let lookupSlug = ''
let lookupResult: LookupResult | null = null
let lookupSeq = 0
let showJobs = false
const lookupCache = new Map<string, LookupResult>()

const kindLabel = (k: PageKind): string => (k === 'job' ? 'Save job' : k === 'profile' ? 'Save profile' : 'Open a job or profile')
const here = (): PageKind => pageOf(location.href).kind
let pillEl: HTMLButtonElement | null = null
/** LinkedIn changes the URL without a reload; the label follows the live URL, never a cached one. */
const refreshLabel = (): void => {
  if (!pillEl) return
  const k = here()
  pillEl.textContent = busy || kindLabel(k)
  pillEl.setAttribute('class', k === 'other' ? 'pill idle' : 'pill save')
  pillEl.setAttribute('aria-disabled', String(k === 'other'))
}

async function api(path: string, method: 'GET' | 'POST' | 'PATCH' | 'DELETE', body?: unknown): Promise<ApiResult> {
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

/** The slug comes from the address path only, never the page; the same slug is not asked twice. */
async function refreshLookup(): Promise<void> {
  const slug = pageOf(location.href).kind === 'profile' ? slugFromPath(location.pathname) : ''
  if (slug === lookupSlug) return
  lookupSlug = slug
  lookupResult = slug ? (lookupCache.get(slug) ?? null) : null
  showJobs = false
  render()
  if (!slug || lookupCache.has(slug)) return
  const seq = ++lookupSeq
  const cfg = (await chrome.runtime.sendMessage({ type: 'config' })) as { app: string; paired: boolean }
  appUrl = cfg.app
  paired = cfg.paired
  if (!cfg.paired) return // no token: no call, no message
  const r = await api(lookupPath(slug), 'GET')
  if (!r.ok || seq !== lookupSeq || slug !== lookupSlug) return // the app is down or the page moved on: show nothing
  lookupCache.set(slug, r.data as LookupResult)
  lookupResult = r.data as LookupResult
  render()
}

function reset(): void {
  jobResult = null
  jobTyped = {}
  person = null
  companyTyped = ''
  paste = ''
  showPaste = false
  undone = ''
  message = ''
}

/** The click (or the shortcut): save what this page is, right now. */
async function start(): Promise<void> {
  const kind = here()
  open = true
  collapsed = false
  reset()
  const cfg = (await chrome.runtime.sendMessage({ type: 'config' })) as { app: string; paired: boolean }
  appUrl = cfg.app
  paired = cfg.paired
  last = extract(document, location)
  if (kind === 'other') message = 'Open a LinkedIn job or profile, then press again.'
  else if (!paired) message = 'Not paired yet: open the extension options and paste your token.'
  else if (kind === 'job') await saveJob()
  else await saveProfile()
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

async function saveProfile(): Promise<void> {
  busy = 'Saving the profile…'
  render()
  const x = paste ? null : extract(document, location, true)
  last = extract(document, location)
  const r = await api('/ext/person', 'POST', {
    payload: x?.payload ?? null,
    paste: paste || null,
    url: location.href.split('?')[0],
    company: companyTyped || null,
    extension_version: EXT_VERSION,
  })
  busy = ''
  if (r.ok) {
    person = r.data as PersonOut
    if (person.saved && person.linked) {
      const slug = slugFromPath(location.pathname)
      if (slug) lookupCache.set(slug, person.linked)
      lookupSlug = slug
      lookupResult = person.linked
    }
    if (!person.saved) message = ''
  } else message = failure(r)
}

/** After saving, role and alum are corrections applied at once (nothing to confirm). */
async function correct(patch: { persona?: string; alumni?: boolean }): Promise<void> {
  if (!person?.contact_id) return
  const r = await api(`/ext/person/${person.contact_id}`, 'PATCH', patch)
  if (r.ok) {
    const d = r.data as { persona: string; alumni: boolean }
    person = { ...person, persona: d.persona, alumni: d.alumni, persona_reasons: patch.persona ? ['set by you'] : person.persona_reasons }
  } else message = failure(r)
}

async function undoSave(): Promise<void> {
  const kind = here()
  if (kind === 'job' && jobResult?.job_id) {
    const r = await api(`/ext/job/${jobResult.job_id}`, 'DELETE')
    if (r.ok) {
      undone = 'Undone: the job was dismissed.'
      jobResult = null
    } else message = failure(r)
  } else if (kind === 'profile' && person?.contact_id) {
    const r = await api(`/ext/person/${person.contact_id}`, 'DELETE')
    if (r.ok) {
      undone = 'Undone: the person was removed.'
      person = null
    } else message = failure(r)
  }
}

// ----------------------------------------------------------------------------- rendering

function button(label: string, onClick: () => void, cls = ''): HTMLButtonElement {
  const b = h('button', { type: 'button', ...(cls ? { class: cls } : {}) }, label)
  b.addEventListener('click', onClick)
  return b
}

const redo = (fn: () => Promise<void>) => () => void fn().then(render)

const FROM: Record<string, string> = { title: 'the tab title', page: 'the page', you: 'you', url: 'the address', missing: 'not found' }

function flagLines(flags: Flag[]): Node[] {
  if (!flags.length) return [h('div', { class: 'small ok' }, 'Nothing looks off.')]
  return [h('div', { class: 'warn' }, 'Flagged for review in the app:'), ...flags.map((f) => h('div', { class: 'warn' }, `• ${f.text}`))]
}

function openLink(path: string): Node {
  return h('a', { href: `${appUrl}${path}`, target: '_blank', rel: 'noreferrer' }, 'Open in the app')
}

/** Next to the Save profile pill: the saved person's jobs in the app (a link opens a new tab). */
function lookupView(): Node | null {
  const v = viewOf(lookupResult)
  const link = (path: string, cls: string, label: string): HTMLAnchorElement => h('a', { href: `${appUrl}${path}`, target: '_blank', rel: 'noreferrer', class: cls }, label)
  if (v.kind === 'one') return link(jobPath(v.job), 'pill link', 'View jobs associated with profile')
  if (v.kind === 'saved_no_job') return h('div', { class: 'small' }, 'Saved, no job linked yet')
  if (v.kind === 'many') {
    const toggle = h('button', { type: 'button', class: 'pill save', 'aria-expanded': String(showJobs) }, 'View jobs associated with profile')
    toggle.addEventListener('click', () => {
      showJobs = !showJobs
      render()
    })
    const box = h('div', { class: 'stack' }, ...(showJobs ? [h('div', { class: 'jobs' }, ...v.jobs.map((j) => h('a', { href: `${appUrl}${jobPath(j)}`, target: '_blank', rel: 'noreferrer' }, `${j.title} · ${j.company} · ${statusLabel(j.status)}`)))] : []), toggle)
    return box
  }
  return null
}

function jobView(): Node[] {
  const out: Node[] = []
  const r = jobResult
  if (r?.saved) {
    out.push(h('h3', {}, `Saved · ${r.parsed.title} @ ${r.parsed.company}`))
    out.push(h('div', { class: 'small' }, `Title and company: from ${FROM[r.sources.title] ?? 'the tab title'}`))
    const where = [r.parsed.location, r.parsed.workplace].filter(Boolean).join(' · ')
    out.push(h('div', { class: 'small' }, where ? `Location: ${where} (from ${FROM[r.sources.location] ?? 'the page'})` : 'Location: not found'))
    out.push(h('div', { class: 'small' }, `Description: ${r.description_chars.toLocaleString()} characters (${r.description_level === 'full' ? 'full listing' : 'snippet'})`))
    out.push(h('div', { class: 'small' }, r.duplicate_of ? 'Merged into a listing you already had.' : r.created ? 'New job, scoring now.' : 'Already saved: updated.'))
    out.push(...flagLines(r.flags))
    // Warnings the flags above already say (collapsed, short, no country) are not repeated.
    for (const w of r.warnings.filter((x) => !/collapsed|is short|No country found|summary tag/.test(x))) out.push(h('div', { class: 'small' }, w))
    const btns = h('div', { class: 'btns' })
    if (r.undo) btns.append(button('Undo', redo(undoSave)))
    out.push(btns)
    if (r.job_id) out.push(openLink(`/linkedin?view=jobs&job=${r.job_id}`))
  } else if (r && r.missing.length) {
    out.push(h('h3', {}, 'Not saved: the page did not give'))
    for (const field of r.missing) {
      const input = field === 'description' ? h('textarea', { 'aria-label': field }) : h('input', { type: 'text', 'aria-label': field })
      input.value = jobTyped[field] ?? r.parsed[field] ?? ''
      input.addEventListener('input', () => {
        jobTyped[field] = input.value
      })
      out.push(h('div', { class: 'small' }, field), input)
    }
    out.push(h('div', { class: 'btns' }, button('Save', redo(saveJob), 'primary')))
  }
  return out
}

function profileView(): Node[] {
  const out: Node[] = []
  const p = person
  if (!p) return out
  if (!p.saved) {
    out.push(h('h3', {}, 'Not saved: the page did not give'), h('div', { class: 'small' }, p.missing.join(', ')))
    if (p.missing.includes('company')) {
      const company = h('input', { type: 'text', 'aria-label': 'Company', placeholder: 'Company' })
      company.value = companyTyped
      company.addEventListener('input', () => {
        companyTyped = company.value.trim()
      })
      out.push(company, h('div', { class: 'btns' }, button('Save', redo(saveProfile), 'primary')))
    }
    return out
  }
  out.push(h('h3', {}, `Saved · ${p.name}`))
  const line = [p.current_title || p.headline, p.current_company].filter(Boolean).join(' @ ')
  if (line) out.push(h('div', { class: 'small' }, line))
  if (p.location) out.push(h('div', { class: 'small' }, p.location))
  if (p.do_not_contact) out.push(h('div', { class: 'warn' }, p.do_not_contact))
  const chips = h('div', { class: 'btns' })
  for (const [value, label] of [['recruiter', 'Recruiter'], ['lead', 'Team lead'], ['peer', 'Peer']] as const) {
    chips.append(
      button(label, redo(() => correct({ persona: value }))),
    )
    chips.lastElementChild?.setAttribute('aria-pressed', String(p.persona === value))
  }
  out.push(h('div', { class: 'small' }, `Role (${p.persona_reasons.join('; ') || 'detected from the title'}):`), chips)
  const alum = h('input', { type: 'checkbox' })
  alum.checked = p.alumni
  alum.addEventListener('change', () => void correct({ alumni: alum.checked }).then(render))
  out.push(h('label', { class: 'row' }, alum, `${p.school ?? 'School'} alum`))
  out.push(h('div', { class: 'small' }, p.job ? `Joined: ${p.job.title} (${p.job.stage})` : 'No open job at this company yet: they join the next job you save there.'))
  out.push(...flagLines(p.flags))
  const btns = h('div', { class: 'btns' })
  if (p.undo) btns.append(button('Undo', redo(undoSave)))
  out.push(btns, openLink('/linkedin?view=profiles'))
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
  ta.value = paste
  return [
    ta,
    button(
      'Save pasted text',
      redo(async () => {
        paste = ta.value
        message = ''
        await saveProfile()
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
      if (undone) panel.append(h('div', { class: 'small' }, undone))
      if (message) {
        panel.append(h('div', { class: 'warn' }, message))
        if (!paired || message.startsWith('The app refused')) panel.append(button('Open extension options', () => void chrome.runtime.sendMessage({ type: 'options' })))
      }
      if (kind === 'job') panel.append(...jobView())
      if (kind === 'profile') {
        panel.append(...profileView())
        if (message || (person && !person.saved) || (!person && !undone)) panel.append(...pasteView())
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
  const jobsLink = kind === 'profile' && !collapsed ? lookupView() : null
  if (jobsLink) wrap.append(jobsLink)
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
    const pill = h('button', { type: 'button', class: kind === 'other' ? 'pill idle' : 'pill save', 'aria-disabled': String(kind === 'other') }, busy || kindLabel(kind))
    pillEl = pill
    pill.addEventListener('pointerenter', refreshLabel)
    pill.addEventListener('focus', refreshLabel)
    // On an unrelated page the button is dimmed but still re-checks the address, so a missed navigation recovers.
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
    void refreshLookup()
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
const onNavigate = (): void => {
  refreshLabel()
  void refreshLookup()
}
window.addEventListener('popstate', onNavigate)
;(window as unknown as { navigation?: EventTarget }).navigation?.addEventListener('currententrychange', onNavigate)

void chrome.storage.local.get('includeText').then((v) => {
  includeText = v.includeText === true
})
document.documentElement.append(root)
render()
void refreshLookup()
