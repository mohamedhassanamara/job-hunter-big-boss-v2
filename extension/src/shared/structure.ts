/** "Copy page structure": a redacted skeleton of <main> so a layout change can be understood without sharing
 * the page. Tags, roles, link path shapes and text lengths; no class names are read. */
import { labels } from './labels'
import { linkShape } from './urls'
import { norm } from './text'

interface Node_ {
  t: string
  role?: string
  level?: string
  view?: string
  href?: string
  text?: string
  k?: Node_ | Node_[]
}

const MAX_DEPTH = 14
const MAX_NODES = 600

export function skeleton(doc: Document, includeText: boolean): string {
  const L = labels()
  const known = new Set([L.jobAbout, L.jobTeam, L.contact, ...Object.values(L.sections), 'Message', 'Connect', 'Follow', 'More', 'Save', 'Apply', 'Easy Apply', 'Show all', 'Show more', 'See more', '·', '1st', '2nd', '3rd', '3rd+'].map(norm))
  let count = 0
  const walk = (e: Element, depth: number): Node_ | null => {
    if (count++ > MAX_NODES || depth > MAX_DEPTH) return null
    const kids = Array.from(e.children).map((c) => walk(c, depth + 1)).filter((x): x is Node_ => !!x)
    const own = Array.from(e.childNodes)
      .filter((n) => n.nodeType === 3)
      .map((n) => (n.textContent ?? '').trim())
      .join(' ')
      .trim()
    const tag = e.tagName
    if (!kids.length && !own && !['A', 'BUTTON', 'IMG', 'SECTION', 'H1', 'H2', 'H3', 'LI', 'UL'].includes(tag)) return null
    const n: Node_ = { t: tag.toLowerCase() }
    const role = e.getAttribute('role')
    if (role) n.role = role
    const level = e.getAttribute('aria-level')
    if (level) n.level = level
    const view = e.getAttribute('data-view-name')
    if (view && view.length < 40) n.view = view
    if (tag === 'A') n.href = linkShape(e.getAttribute('href') ?? '')?.shape ?? '(other link)'
    if (own) n.text = includeText || known.has(norm(own)) ? own : `<${own.length} chars>`
    if (kids.length) n.k = kids.length === 1 && !own && !n.href ? kids[0] : kids
    return n
  }
  const root = doc.querySelector('main') ?? doc.body
  return JSON.stringify({ tool: 'jh-structure', version: 1, includeText, h1: doc.querySelectorAll('h1').length, capped: count > MAX_NODES, tree: walk(root, 0) }, null, 1)
}
