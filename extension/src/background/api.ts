/**
 * The ONLY file in the extension that touches the network, and only your own app on this computer:
 * `http://localhost` / `http://127.0.0.1` (any port), the `/api/ext/*` routes, with the token from
 * Options. The token never reaches a LinkedIn page: the content script asks the worker to call.
 */
export interface Config {
  api: string
  app: string
  token: string
}

export const DEFAULTS = { api: 'http://localhost:8000', app: 'http://localhost:5173' }

/** The origin when `url` is plain http on localhost / 127.0.0.1, else null (nothing else is ever called). */
export function localOrigin(url: string): string | null {
  try {
    const u = new URL(url)
    return u.protocol === 'http:' && (u.hostname === 'localhost' || u.hostname === '127.0.0.1') ? u.origin : null
  } catch {
    return null
  }
}

export async function config(): Promise<Config> {
  const v = await chrome.storage.local.get('config')
  const c = (v.config ?? {}) as Partial<Config>
  return { api: c.api || DEFAULTS.api, app: c.app || DEFAULTS.app, token: c.token || '' }
}

export interface ApiResult {
  ok: boolean
  status: number
  data: unknown
  error?: string
}

export async function call(path: string, method: 'GET' | 'POST' | 'PATCH', body?: unknown): Promise<ApiResult> {
  const c = await config()
  const origin = localOrigin(c.api)
  if (!origin) return { ok: false, status: 0, data: null, error: 'The app address must be http://localhost or http://127.0.0.1' }
  if (!c.token) return { ok: false, status: 0, data: null, error: 'no-token' }
  if (!path.startsWith('/ext/')) return { ok: false, status: 0, data: null, error: 'Only /ext/ routes are allowed' }
  try {
    const res = await fetch(`${origin}/api${path}`, {
      method,
      headers: { Authorization: `Bearer ${c.token}`, ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    let data: unknown = null
    try {
      data = await res.json()
    } catch {
      /* no body */
    }
    return { ok: res.ok, status: res.status, data }
  } catch {
    return { ok: false, status: 0, data: null, error: 'unreachable' }
  }
}
