export type PageKind = 'job' | 'profile' | 'other'

export interface PageRef {
  kind: PageKind
  id: string // job id or profile slug
}

/** The page type from the URL only (no DOM). */
export function pageOf(href: string): PageRef {
  let u: URL
  try {
    u = new URL(href)
  } catch {
    return { kind: 'other', id: '' }
  }
  const view = u.pathname.match(/\/jobs\/view\/(?:[^/?#]*?-)?(\d{6,})/)
  if (view) return { kind: 'job', id: view[1] }
  const cur = u.pathname.startsWith('/jobs') ? u.searchParams.get('currentJobId') : null
  if (cur && /^\d{6,}$/.test(cur)) return { kind: 'job', id: cur }
  const prof = u.pathname.match(/^\/in\/([^/]+)/)
  if (prof) return { kind: 'profile', id: prof[1] }
  return { kind: 'other', id: '' }
}

export type LinkKind = 'company' | 'school' | 'person' | 'job'

/** A link's kind and a redacted path shape (ids replaced), or null when it is none of ours. */
export function linkShape(href: string): { kind: LinkKind; shape: string } | null {
  let path: string
  try {
    path = new URL(href, 'https://www.linkedin.com').pathname
  } catch {
    return null
  }
  const m = path.match(/^\/(company|school|in|jobs\/view)\/([^/]+)(\/.*)?$/)
  if (!m) return null
  const kind: LinkKind = m[1] === 'company' ? 'company' : m[1] === 'school' ? 'school' : m[1] === 'in' ? 'person' : 'job'
  return { kind, shape: `/${m[1]}/<id>${m[3] ?? '/'}`.replace(/\d{6,}/g, '<n>') }
}
