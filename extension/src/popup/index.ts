/** Status and the two diagnostic copies. The core loop is the pill on the page; this is a secondary surface. */
const $ = (id: string): HTMLElement => document.getElementById(id) as HTMLElement
const box = $('text') as HTMLInputElement

async function tabId(): Promise<number | null> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  return tab?.id ?? null
}

async function ask<T>(msg: Record<string, unknown>): Promise<T | null> {
  const id = await tabId()
  if (id === null) return null
  try {
    return (await chrome.tabs.sendMessage(id, msg)) as T
  } catch {
    return null
  }
}

function note(text: string): void {
  $('note').textContent = text
}

async function init(): Promise<void> {
  box.checked = (await chrome.storage.local.get('includeText')).includeText === true
  box.addEventListener('change', () => void chrome.storage.local.set({ includeText: box.checked }))
  const info = await ask<{ page: string }>({ type: 'info' })
  $('status').textContent = info ? `LinkedIn page type: ${info.page}` : 'Not on a LinkedIn page (or reload the tab once)'

  $('check').addEventListener('click', async () => {
    const r = await ask<{ page: string; anchors: { name: string; ok: boolean; note?: string }[] }>({ type: 'check', includeText: box.checked })
    const el = $('anchors')
    el.replaceChildren()
    for (const a of r?.anchors ?? []) {
      const row = document.createElement('div')
      const mark = document.createElement('span')
      mark.setAttribute('class', a.ok ? 'ok' : 'no')
      mark.textContent = a.ok ? '✓ ' : '✗ '
      row.append(mark, a.name + (a.note ? ` (${a.note})` : ''))
      el.append(row)
    }
    note(r ? 'Checked.' : 'No LinkedIn page here.')
  })
  const copyOf = (id: string, type: string, field: string) =>
    $(id).addEventListener('click', async () => {
      const r = await ask<Record<string, string>>({ type, includeText: box.checked })
      if (!r?.[field]) return note('No LinkedIn page here.')
      await navigator.clipboard.writeText(r[field])
      note('Copied.')
    })
  copyOf('report', 'check', 'report')
  copyOf('structure', 'structure', 'structure')
}
void init()
