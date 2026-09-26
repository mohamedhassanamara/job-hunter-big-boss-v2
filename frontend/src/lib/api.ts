export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

type Json = Record<string, unknown> | unknown[]

async function request<T>(method: string, path: string, body?: Json | FormData): Promise<T> {
  const isForm = body instanceof FormData
  let res: Response
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers: body && !isForm ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
    })
  } catch {
    throw new ApiError(0, "Can't reach the API. Is the backend running?")
  }
  if (!res.ok) {
    let message = `Request failed (${res.status})`
    try {
      const data = await res.json()
      if (typeof data.detail === 'string') message = data.detail
    } catch {
      // A non-JSON 5xx means the dev proxy couldn't reach the backend.
      if (res.status >= 500) message = "Can't reach the API. Is the backend running?"
    }
    throw new ApiError(res.status, message)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: Json | FormData) => request<T>('POST', path, body),
  put: <T>(path: string, body: Json) => request<T>('PUT', path, body),
  patch: <T>(path: string, body: Json) => request<T>('PATCH', path, body),
  del: <T>(path: string) => request<T>('DELETE', path),
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
