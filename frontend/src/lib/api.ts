import { setUsageDemo, trackRequest } from './usage'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

type Json = Record<string, unknown> | unknown[]

/**
 * Which backend workspace requests go to. `demo` is the tour sandbox (sample data only);
 * everything else always hits the real workspace.
 */
export type Workspace = 'real' | 'demo'
let workspace: Workspace = 'real'

export function setWorkspace(next: Workspace) {
  workspace = next
  setUsageDemo(next === 'demo')
}

export function getWorkspace(): Workspace {
  return workspace
}

async function request<T>(method: string, path: string, body?: Json | FormData): Promise<T> {
  const isForm = body instanceof FormData
  let res: Response
  const started = performance.now()
  try {
    const headers: Record<string, string> = {}
    if (body && !isForm) headers['Content-Type'] = 'application/json'
    if (workspace === 'demo') headers['X-Workspace'] = 'demo'
    res = await fetch(`/api${path}`, {
      method,
      headers,
      body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
    })
  } catch {
    throw new ApiError(0, "Can't reach the API. Is the backend running?")
  }
  trackRequest(method, path, performance.now() - started, res.ok)
  if (!res.ok) {
    let message = `Request failed (${res.status})`
    try {
      const data = await res.json()
      if (typeof data.detail === 'string') message = data.detail
    } catch {
      // A non-JSON 5xx means the dev proxy couldn't reach the backend.
      if (res.status === 502 || res.status === 504) message = "Can't reach the API. Is the backend running?"
      else if (res.status >= 500) message = `Server error (${res.status}). Check the backend logs.`
    }
    throw new ApiError(res.status, message)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

/** POST, then read the response body as text chunks as they arrive (the Copilot's answers). */
async function stream(path: string, body: Json, onChunk: (text: string) => void): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (workspace === 'demo') headers['X-Workspace'] = 'demo'
  let res: Response
  try {
    res = await fetch(`/api${path}`, { method: 'POST', headers, body: JSON.stringify(body) })
  } catch {
    throw new ApiError(0, "Can't reach the API. Is the backend running?")
  }
  if (!res.ok || !res.body) {
    let message = `Request failed (${res.status})`
    try {
      const data = await res.json()
      if (typeof data.detail === 'string') message = data.detail
    } catch {
      // not JSON
    }
    throw new ApiError(res.status, message)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    onChunk(decoder.decode(value, { stream: true }))
  }
}

export const api = {
  stream,
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: Json | FormData) => request<T>('POST', path, body),
  put: <T>(path: string, body: Json) => request<T>('PUT', path, body),
  patch: <T>(path: string, body: Json) => request<T>('PATCH', path, body),
  del: <T>(path: string) => request<T>('DELETE', path),
}

/** A GET URL for places that can't send headers (iframe, download link): the workspace goes in
 * the query string. */
export function apiUrl(path: string, params: Record<string, string | number | boolean> = {}): string {
  const all: Record<string, string> = Object.fromEntries(Object.entries(params).map(([k, v]) => [k, String(v)]))
  if (workspace === 'demo') all.workspace = 'demo'
  const query = new URLSearchParams(all).toString()
  return `/api${path}${query ? `?${query}` : ''}`
}

/** Build a query string, skipping empty values and repeating array params. */
export function qs(params: Record<string, string | number | boolean | string[] | null | undefined>) {
  const sp = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '' || value === false) continue
    if (Array.isArray(value)) value.forEach((v) => sp.append(key, v))
    else sp.set(key, String(value))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}
