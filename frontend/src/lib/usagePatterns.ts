/** What the local usage log may record: route patterns and action names, never page content. */

export type RefKind = 'job' | 'app' | 'cv' | 'draft'

const TAB_KEYS = ['tab', 'view', 'section']
const SLUG = /^[a-z0-9-]{1,24}$/

/** `/jobs/123/cv?tab=x&q=secret` → `/jobs/:id/cv?tab=x`; only whitelisted query keys with slug values. */
export function screenPattern(pathname: string, search = ''): { name: string; jobId: number | null } {
  const path = pathname.replace(/\/\d+(?=\/|$)/g, '/:id') || '/'
  const params = new URLSearchParams(search)
  const kept = TAB_KEYS.flatMap((k) => {
    const v = params.get(k)
    return v && SLUG.test(v) ? [`${k}=${v}`] : []
  })
  const job = /^\/jobs\/(\d+)(?:\/|$)/.exec(pathname)
  return { name: kept.length ? `${path}?${kept.join('&')}` : path, jobId: job ? Number(job[1]) : null }
}

/** `/applications/42/cv/generate?x=1` → `/applications/:id/cv/generate`; odd segments become `:x`. */
export function requestPattern(path: string): string {
  const clean = path.split('?')[0]
  return clean
    .split('/')
    .map((seg) => (/^\d+$/.test(seg) ? ':id' : seg.length > 24 || /\d/.test(seg) ? ':x' : seg))
    .join('/')
}

interface ActionRule {
  method: string
  pattern: RegExp
  name: string
  ref: RefKind | null
}

/** The key actions, by endpoint. Client-only ones (open_listing) are logged where they happen. */
export const ACTIONS: ActionRule[] = [
  { method: 'POST', pattern: /^\/jobs\/(\d+)\/shortlist$/, name: 'shortlist', ref: 'job' },
  { method: 'POST', pattern: /^\/jobs\/(\d+)\/dismiss$/, name: 'dismiss', ref: 'job' },
  { method: 'POST', pattern: /^\/cv\/(\d+)\/approve$/, name: 'approve_cv', ref: 'cv' },
  { method: 'POST', pattern: /^\/applications\/(\d+)\/cv\/generate$/, name: 'generate_cv', ref: 'app' },
  { method: 'POST', pattern: /^\/cv\/(\d+)\/(summary|revise-summary)$/, name: 'new_summary', ref: 'cv' },
  { method: 'POST', pattern: /^\/applications\/(\d+)\/draft\/generate$/, name: 'generate_email', ref: 'app' },
  { method: 'POST', pattern: /^\/outreach\/drafts\/(\d+)\/approve$/, name: 'approve_email', ref: 'draft' },
  { method: 'POST', pattern: /^\/outreach\/drafts\/(\d+)\/approve-unverified$/, name: 'approve_email_unverified', ref: 'draft' },
  { method: 'POST', pattern: /^\/outreach\/drafts\/(\d+)\/queue$/, name: 'queue_add', ref: 'draft' },
  { method: 'POST', pattern: /^\/queue\/resume$/, name: 'queue_start', ref: null },
  { method: 'POST', pattern: /^\/applications\/(\d+)\/applied$/, name: 'mark_applied', ref: 'app' },
  { method: 'POST', pattern: /^\/applications\/(\d+)\/sent-manually$/, name: 'sent_manually', ref: 'app' },
]

export function matchAction(method: string, path: string): { name: string; ref: { kind: RefKind; id: number } | null } | null {
  const clean = path.split('?')[0]
  for (const rule of ACTIONS) {
    if (rule.method !== method) continue
    const m = rule.pattern.exec(clean)
    if (m) return { name: rule.name, ref: rule.ref && m[1] ? { kind: rule.ref, id: Number(m[1]) } : null }
  }
  return null
}
