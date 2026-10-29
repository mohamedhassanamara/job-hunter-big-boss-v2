/** Pairing: the token, and where your app runs. Saved in this browser only (chrome.storage.local). */
import { DEFAULTS, config, localOrigin } from '../background/api'

const $ = (id: string): HTMLInputElement => document.getElementById(id) as HTMLInputElement
const result = (text: string, ok?: boolean): void => {
  const el = document.getElementById('result') as HTMLElement
  el.textContent = text
  el.setAttribute('class', ok === undefined ? 'small' : ok ? 'small ok' : 'small no')
}

async function load(): Promise<void> {
  const c = await config()
  $('token').value = c.token
  $('api').value = c.api
  $('app').value = c.app
}

async function save(): Promise<boolean> {
  const api = $('api').value.trim() || DEFAULTS.api
  const app = $('app').value.trim() || DEFAULTS.app
  if (!localOrigin(api) || !localOrigin(app)) {
    result('Both addresses must be http://localhost or http://127.0.0.1 (with the port).', false)
    return false
  }
  await chrome.storage.local.set({ config: { api: localOrigin(api), app: localOrigin(app), token: $('token').value.trim() } })
  result('Saved.', true)
  return true
}

$('save').addEventListener('click', () => void save())
$('test').addEventListener('click', async () => {
  if (!(await save())) return
  const r = (await chrome.runtime.sendMessage({ type: 'api', path: '/ext/ping', method: 'GET' })) as { ok: boolean; status: number; data: { jobs_captured_today?: number; people_total?: number } | null; error?: string }
  if (r.ok) result(`Connected. Today: ${r.data?.jobs_captured_today ?? 0} job(s) captured; ${r.data?.people_total ?? 0} LinkedIn people in the app.`, true)
  else if (r.status === 401) result('The app refused this token: create a new one in Settings → LinkedIn.', false)
  else if (r.error === 'no-token') result('Paste your token first.', false)
  else result('Could not reach the app: is it running (make dev) and is the address right?', false)
})
void load()
