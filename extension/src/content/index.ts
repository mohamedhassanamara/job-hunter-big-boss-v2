/**
 * The floating control. It reads the page ONLY inside a click (or the keyboard shortcut / popup request),
 * never on a timer or by observing the page, and never clicks, scrolls or requests anything.
 * Before the Phase 2a gate it only checks anchors and copies redacted reports: nothing is saved anywhere.
 */
import { extract, type Extraction } from '../shared/extract'
import { buildReport } from '../shared/report'
import { skeleton } from '../shared/structure'
import { pageOf, type PageKind } from '../shared/urls'

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
  .pill:disabled { opacity: .6; cursor: default }
  .dot { width: 14px; height: 14px; padding: 0 }
  .panel { width: 340px; max-height: 70vh; overflow: auto; border: 1px solid GrayText; background: Canvas; border-radius: 10px; padding: 12px; box-shadow: 0 2px 14px rgb(0 0 0 / 30%) }
  .row { display: flex; gap: 6px; align-items: baseline } .ok { color: #1a7f37 } .no { color: #cf222e }
  .small { font-size: 12px; color: GrayText } .btns { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px }
  button { cursor: pointer; border: 1px solid GrayText; background: Canvas; border-radius: 6px; padding: 4px 8px }
`

const root = h('div')
const shadow = root.attachShadow({ mode: 'closed' })
let open = false
let collapsed = false
let last: Extraction | null = null
let includeText = false
let note = ''

const kindLabel = (k: PageKind): string => (k === 'job' ? 'Check job page' : k === 'profile' ? 'Check profile' : 'Open a job or profile')
const here = (): PageKind => pageOf(location.href).kind
let pillEl: HTMLButtonElement | null = null
/** LinkedIn changes the URL without a reload; the label follows the live URL, never a cached one. */
const refreshLabel = (): void => {
  if (pillEl) pillEl.textContent = kindLabel(here())
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

function run(): Extraction {
  last = extract(document, location)
  return last
}

function render(): void {
  const kind = here()
  const style = h('style')
  style.textContent = STYLE
  const wrap = h('div', { class: 'wrap' })
  if (open && last) {
    const rows = last.anchors.map((a) => h('div', { class: 'row' }, h('span', { class: a.ok ? 'ok' : 'no' }, a.ok ? '✓' : '✗'), h('span', {}, a.name + (a.note ? ` (${a.note})` : ''))))
    const box = h('input', { type: 'checkbox' })
    box.checked = includeText
    box.addEventListener('change', () => {
      includeText = box.checked
      void chrome.storage.local.set({ includeText })
    })
    const mk = (label: string, fn: () => string) => {
      const b = h('button', {}, label)
      b.addEventListener('click', () => {
        void copy(fn()).then((ok) => {
          note = ok ? `${label}: copied` : `${label}: copy failed`
          render()
        })
      })
      return b
    }
    const close = h('button', {}, 'Close')
    close.addEventListener('click', () => {
      open = false
      render()
    })
    wrap.append(
      h(
        'div',
        { class: 'panel' },
        h('strong', {}, `Anchor check · ${last.page}`),
        ...(last.page === 'other' ? [h('div', { class: 'small' }, `Not recognised as a job or profile page: ${location.pathname.replace(/\d{6,}/g, '<n>')}`)] : []),
        ...rows,
        h('div', { class: 'btns' }, mk('Copy report', () => buildReport(run(), includeText)), mk('Copy page structure', () => skeleton(document, includeText)), close),
        h('label', { class: 'small' }, box, ' Include page text (only on your own pages)'),
        h('div', { class: 'small' }, note || 'Nothing is saved or sent anywhere. Reports are redacted unless you tick the box.'),
      ),
    )
  }
  if (collapsed) {
    const d = h('button', { class: 'pill dot', title: 'Job Hunter' })
    d.addEventListener('click', () => {
      collapsed = false
      render()
    })
    wrap.append(d)
  } else {
    const pill = h('button', { class: 'pill' }, kindLabel(kind))
    pillEl = pill
    pill.addEventListener('pointerenter', refreshLabel)
    pill.addEventListener('focus', refreshLabel)
    pill.addEventListener('click', () => {
      run()
      open = true
      note = ''
      render()
    })
    const hide = h('button', { class: 'small', title: 'Collapse' }, '–')
    hide.addEventListener('click', () => {
      collapsed = true
      open = false
      render()
    })
    wrap.append(h('div', { class: 'row' }, pill, hide))
  }
  shadow.replaceChildren(style, wrap)
}

chrome.runtime.onMessage.addListener((raw, _sender, send) => {
  const msg = raw as { type: string; includeText?: boolean }
  if (msg.type === 'url') {
    open = false
    last = null
    render()
  } else if (msg.type === 'command') {
    if (here() !== 'other') {
      run()
      open = true
      collapsed = false
      note = ''
    }
    render()
  } else if (msg.type === 'info') {
    send({ page: here() })
  } else if (msg.type === 'check') {
    const x = run()
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
