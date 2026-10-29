/** Text helpers. Nothing here reads a CSS class. */

/** Unicode NFKC, lower-case, accents stripped, whitespace collapsed, trailing punctuation removed. */
export function norm(text: string): string {
  return collapseDoubled(text)
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .normalize('NFKC')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .replace(/[\s.:;,]+$/g, '')
    .trim()
}

/** "ExperienceExperience" / "Experience Experience" -> "Experience" (a visible and a screen-reader copy). */
export function collapseDoubled(text: string): string {
  const t = text.replace(/\s+/g, ' ').trim()
  if (t.length >= 2 && t.length % 2 === 0) {
    const h = t.length / 2
    if (t.slice(0, h) === t.slice(h)) return t.slice(0, h)
  }
  const m = t.match(/^(.+?) \1$/)
  return m ? m[1] : t
}

const BLOCK = new Set(['P', 'DIV', 'LI', 'UL', 'OL', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'SECTION', 'ARTICLE', 'HEADER', 'FOOTER', 'TR', 'BLOCKQUOTE'])
const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'SVG', 'TEMPLATE'])

/** Block-aware text of a (possibly detached) node: newlines at block boundaries, "• " before list items. No innerHTML. */
export function toText(node: Node): string {
  const out: string[] = []
  const visit = (n: Node) => {
    if (n.nodeType === 3) {
      out.push(n.textContent ?? '')
      return
    }
    if (n.nodeType !== 1 && n.nodeType !== 11) return
    const el = n as Element
    const tag = n.nodeType === 1 ? el.tagName.toUpperCase() : ''
    if (SKIP.has(tag)) return
    if (tag === 'BR') {
      out.push('\n')
      return
    }
    const block = BLOCK.has(tag)
    if (block) out.push('\n')
    if (tag === 'LI') out.push('• ')
    n.childNodes.forEach(visit)
    if (block) out.push('\n')
  }
  visit(node)
  return out
    .join('')
    .replace(/[ \t ]+/g, ' ')
    .replace(/ ?\n ?/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

export const toLines = (text: string): string[] =>
  text
    .split('\n')
    .map((l) => collapseDoubled(l))
    .filter(Boolean)

export const firstLine = (text: string): string => toLines(text)[0] ?? ''

const INLINE = new Set(['inline', 'inline-block', 'contents', 'ruby', 'ruby-text'])

/** Rendered text of a live range, one line per block container (decided by computed `display`, never by a
 * class or tag name): inline neighbours join, block/flex/list-item containers break, <br> breaks. */
export function textOfRange(root: Element, range: Range): string {
  const doc = root.ownerDocument
  const win = doc.defaultView
  if (!win) return ''
  const blockOf = (el: Element): Element => {
    let e: Element | null = el
    while (e && e !== root) {
      if (!INLINE.has(win.getComputedStyle(e).display)) return e
      e = e.parentElement
    }
    return root
  }
  const lines: string[] = []
  let cur = ''
  let lastBlock: Element | null = null
  let lastLi: Element | null = null
  const flush = () => {
    if (cur.trim()) lines.push(cur.replace(/\s+/g, ' ').trim())
    cur = ''
  }
  const walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT)
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    if (!range.isPointInRange(n, 0)) continue
    if (n.nodeType === 1) {
      if ((n as Element).tagName === 'BR') flush()
      continue
    }
    const parent = n.parentElement
    if (!parent || SKIP.has(parent.tagName.toUpperCase())) continue
    const style = win.getComputedStyle(parent)
    if (style.display === 'none' || style.visibility === 'hidden') continue
    const text = n.textContent ?? ''
    if (!text.trim() && !cur) continue
    const block = blockOf(parent)
    if (block !== lastBlock) flush()
    lastBlock = block
    if (!cur) {
      const li = parent.closest('li')
      if (li && li !== lastLi) cur = '• '
      lastLi = li
    }
    cur += text
  }
  flush()
  return lines.join('\n')
}
