/**
 * The thin extractor (docs/LINKEDIN_EXTENSION_DESIGN.md §2.8). It anchors on the tab title, the URL, exact
 * heading text, link shapes and document-order regions. It never reads a CSS class and never changes the page.
 * Interpretation (location, headline, persona…) is the server's job; this only slices the page into regions
 * and reports which anchors were found.
 */
import { labels } from './labels'
import { collapseDoubled, firstLine, norm, textOfRange, toLines } from './text'
import { linkShape, pageOf, type LinkKind, type PageKind } from './urls'

export interface AnchorCheck {
  name: string
  ok: boolean
  note?: string
}
export interface LinkItem {
  kind: LinkKind
  shape: string
  text: string
  region: string
}
export interface Region {
  label: string
  line_count: number
  li_count: number
  lines: string[]
}
export interface JobPayload {
  v: 1
  page: 'job'
  url: string
  job_id: string
  doc_title: string
  title_parsed: string
  company_parsed: string
  header: Region
  about: Region
  team: Region
  links: LinkItem[]
  jsonld_types: string[]
}
export interface ProfilePayload {
  v: 1
  page: 'profile'
  url: string
  slug: string
  doc_title: string
  name_parsed: string
  mode: 'elements' | 'lines' | 'none'
  regions: Region[]
  links: LinkItem[]
}
export interface Extraction {
  page: PageKind
  anchors: AnchorCheck[]
  payload: JobPayload | ProfilePayload | null
}

const MAX_LINES = 60
const MAX_LINE = 200

const follows = (a: Node, b: Node): boolean => !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) && !a.contains(b)
const linkText = (a: Element): string => collapseDoubled(firstLine((a as HTMLElement).innerText || a.textContent || ''))

interface Hit {
  el: Element
  via: 'heading' | 'leaf'
}

/** An element whose exact (normalised) text is `label`: a heading first, then any leaf element. */
function findLabel(root: ParentNode, label: string): Hit | null {
  const want = norm(label)
  for (const h of Array.from(root.querySelectorAll('h1,h2,h3,h4,[role="heading"]'))) {
    if (norm(h.textContent ?? '') === want) return { el: h, via: 'heading' }
  }
  for (const e of Array.from(root.querySelectorAll('*'))) {
    if (!e.children.length && norm(e.textContent ?? '') === want) return { el: e, via: 'leaf' }
  }
  return null
}

/** Everything between two elements in document order (either end may be open). */
function between(root: Element, from: Element | null, to: Element | null): Range {
  const r = root.ownerDocument.createRange()
  if (from) r.setStartAfter(from)
  else r.setStart(root, 0)
  if (to) r.setEndBefore(to)
  else r.setEnd(root, root.childNodes.length)
  return r
}

function region(label: string, root: Element, range: Range): Region {
  const lines = toLines(textOfRange(root, range))
  const li = Array.from(root.querySelectorAll('li')).filter((e) => range.isPointInRange(e, 0)).length
  return { label, line_count: lines.length, li_count: li, lines: lines.slice(0, MAX_LINES).map((l) => l.slice(0, MAX_LINE)) }
}

function inventory(root: Element, bounds: Element[], names: string[]): LinkItem[] {
  const out: LinkItem[] = []
  for (const a of Array.from(root.querySelectorAll('a[href]'))) {
    const s = linkShape(a.getAttribute('href') ?? '')
    if (!s) continue
    const idx = bounds.filter((b) => follows(b, a)).length
    out.push({ kind: s.kind, shape: s.shape, text: linkText(a).slice(0, 120), region: names[idx] ?? 'unknown' })
  }
  return out.slice(0, 200)
}

/** "(3) Title | Company | LinkedIn" -> title (everything before the LAST " | ") and company. */
export function parseJobTitle(docTitle: string): { title: string; company: string } {
  const t = docTitle.replace(/^\(\d+\)\s*/, '').replace(/\s*\|\s*LinkedIn\s*$/i, '').trim()
  const i = t.lastIndexOf(' | ')
  return i < 0 ? { title: t, company: '' } : { title: t.slice(0, i).trim(), company: t.slice(i + 3).trim() }
}

export function parseProfileTitle(docTitle: string): { name: string; extra: boolean } {
  const t = docTitle.replace(/^\(\d+\)\s*/, '').replace(/\s*\|\s*LinkedIn\s*$/i, '').trim()
  const i = t.indexOf(' - ')
  return i < 0 ? { name: t, extra: false } : { name: t.slice(0, i).trim(), extra: true }
}

export function extractJob(doc: Document, loc: Location): Extraction {
  const L = labels()
  const ref = pageOf(loc.href)
  const { title, company } = parseJobTitle(doc.title)
  const main = doc.querySelector('main') ?? doc.body
  const anchors: AnchorCheck[] = []
  anchors.push({ name: 'job id (URL)', ok: !!ref.id })
  anchors.push({ name: 'tab title: title + company', ok: !!title && !!company, note: company ? undefined : 'no " | " in the tab title' })

  const about = findLabel(main, L.jobAbout)
  anchors.push({ name: `"${L.jobAbout}" heading`, ok: !!about, note: about?.via })

  // The detail pane: the smallest ancestor of the About heading that holds a /company/ link matching the title's company.
  let pane: Element = main
  let paneOk = false
  if (about) {
    for (let e = about.el.parentElement; e && e !== doc.documentElement; e = e.parentElement) {
      const hit = Array.from(e.querySelectorAll('a[href]')).some((a) => linkShape(a.getAttribute('href') ?? '')?.kind === 'company' && !!company && norm(linkText(a)) === norm(company))
      if (hit) {
        pane = e
        paneOk = true
        break
      }
    }
  }
  anchors.push({ name: 'detail pane (About heading + matching company link)', ok: paneOk, note: paneOk ? undefined : 'fell back to <main>' })

  const nextH2 = about ? Array.from(pane.querySelectorAll('h2')).find((h) => follows(about.el, h)) ?? null : null
  const none = doc.createRange()
  // The top card (title, company, "location · posted · applicants") sits OUTSIDE the smallest ancestor found above:
  // start the header at the last element before the About heading whose exact text is the tab title.
  let titleEl: Element | null = null
  if (about && title) {
    const want = norm(title)
    const hits = Array.from(main.querySelectorAll('*')).filter((e) => norm(e.textContent ?? '') === want && e.compareDocumentPosition(about.el) & Node.DOCUMENT_POSITION_FOLLOWING && !e.contains(about.el))
    const last = hits[hits.length - 1]
    titleEl = last ? (Array.from(last.querySelectorAll('*')).reverse().find((e) => norm(e.textContent ?? '') === want && !e.children.length) ?? last) : null
  }
  let header: Region
  if (about && titleEl) {
    const r = main.ownerDocument.createRange()
    r.setStartBefore(titleEl)
    r.setEndBefore(about.el)
    const common = r.commonAncestorContainer
    header = region('header', (common.nodeType === Node.ELEMENT_NODE ? common : common.parentElement) as Element, r)
  } else {
    header = region('header', pane, about ? between(pane, null, about.el) : none)
  }
  anchors.push({ name: 'title element before the heading (top card start)', ok: !!titleEl, note: titleEl ? undefined : 'header falls back to the pane start' })
  const aboutRegion = region('about', pane, about ? between(pane, about.el, nextH2) : none)
  anchors.push({ name: 'description text', ok: aboutRegion.line_count > 0, note: `${aboutRegion.lines.join('\n').length} chars` })
  anchors.push({ name: 'header lines before the heading', ok: header.line_count > 0, note: `${header.line_count} lines` })
  // Only the top card carries the location: a " · " line, a lone "·" between split spans, or a workplace word.
  const locAt = header.lines.findIndex((l) => / · |^·$/.test(l) || /\b(remote|hybrid|on-?site)\b/i.test(l))
  anchors.push({ name: 'location/workplace line (" · " or Remote/Hybrid/On-site)', ok: locAt >= 0, note: locAt >= 0 ? `line ${locAt + 1}` : undefined })

  const team = findLabel(pane, L.jobTeam)
  const teamNext = team ? Array.from(pane.querySelectorAll('h2')).find((h) => follows(team.el, h)) ?? null : null
  const teamRegion = team ? region('team', pane, between(pane, team.el, teamNext)) : { label: 'team', line_count: 0, li_count: 0, lines: [] }
  anchors.push({ name: `"${L.jobTeam}" heading`, ok: !!team, note: team ? team.via : 'optional: not every job shows it' })

  const bounds = [about?.el, team?.el].filter((e): e is Element => !!e).sort((a, b) => (follows(a, b) ? -1 : 1))
  const names = bounds.map((b) => (b === about?.el ? 'about' : 'team'))
  const links = inventory(pane, bounds, ['header', ...names])
  anchors.push({ name: 'company link in the pane', ok: links.some((l) => l.kind === 'company') })
  if (team) anchors.push({ name: 'poster link (/in/) after the hiring-team heading', ok: links.some((l) => l.kind === 'person' && l.region === 'team') })

  const jsonld: string[] = []
  doc.querySelectorAll('script[type="application/ld+json"]').forEach((n) => {
    try {
      const j = JSON.parse(n.textContent ?? '')
      for (const x of ([] as unknown[]).concat(j['@graph'] ?? j)) jsonld.push(String((x as { '@type'?: string })['@type'] ?? '?'))
    } catch {
      jsonld.push('unparsable')
    }
  })

  const payload: JobPayload = {
    v: 1,
    page: 'job',
    url: loc.href,
    job_id: ref.id,
    doc_title: doc.title,
    title_parsed: title,
    company_parsed: company,
    header,
    about: aboutRegion,
    team: teamRegion,
    links,
    jsonld_types: jsonld,
  }
  return { page: 'job', anchors, payload }
}

export function extractProfile(doc: Document, loc: Location): Extraction {
  const L = labels()
  const ref = pageOf(loc.href)
  const { name, extra } = parseProfileTitle(doc.title)
  const main = doc.querySelector('main') ?? doc.body
  const anchors: AnchorCheck[] = []
  anchors.push({ name: 'profile URL (/in/<slug>)', ok: !!ref.id })
  anchors.push({ name: 'tab title: name', ok: !!name, note: extra ? 'title has " - ": kept the left part' : undefined })

  const found = Object.entries(L.sections)
    .map(([key, label]) => ({ key, hit: findLabel(main, label) }))
    .filter((x): x is { key: string; hit: Hit } => !!x.hit)
    .sort((a, b) => (follows(a.hit.el, b.hit.el) ? -1 : a.hit.el === b.hit.el ? 0 : 1))
  const unique = found.filter((x, i) => i === 0 || x.hit.el !== found[i - 1].hit.el)

  let mode: ProfilePayload['mode'] = 'none'
  let regions: Region[] = []
  let links: LinkItem[] = []
  if (unique.length) {
    mode = 'elements'
    const els = unique.map((x) => x.hit.el)
    regions.push(region('top', main, between(main, null, els[0])))
    unique.forEach((x, i) => regions.push(region(x.key, main, between(main, x.hit.el, els[i + 1] ?? null))))
    links = inventory(main, els, ['top', ...unique.map((x) => x.key)])
  } else {
    // The elements did not match: split the page's own text lines on exact label lines.
    const text = (main as HTMLElement).innerText ?? ''
    const all = toLines(text)
    const want = new Map(Object.entries(L.sections).map(([k, l]) => [norm(l), k]))
    const cuts = all.map((l, i) => ({ i, key: want.get(norm(l)) })).filter((c): c is { i: number; key: string } => !!c.key)
    if (cuts.length) {
      mode = 'lines'
      const slice = (label: string, a: number, b: number): Region => {
        const lines = all.slice(a, b)
        return { label, line_count: lines.length, li_count: 0, lines: lines.slice(0, MAX_LINES).map((l) => l.slice(0, MAX_LINE)) }
      }
      regions.push(slice('top', 0, cuts[0].i))
      cuts.forEach((c, k) => regions.push(slice(c.key, c.i + 1, cuts[k + 1]?.i ?? all.length)))
      links = inventory(main, [], ['unknown'])
    } else {
      regions = [region('top', main, between(main, null, null))]
      links = inventory(main, [], ['unknown'])
    }
  }
  const top = regions.find((r) => r.label === 'top')?.lines ?? []
  anchors.push({ name: 'section labels found', ok: unique.length > 0 || mode === 'lines', note: `mode=${mode}: ${(mode === 'none' ? [] : regions.filter((r) => r.label !== 'top').map((r) => r.label)).join(', ') || 'none'}` })
  anchors.push({ name: 'name starts a top line', ok: !!name && top.some((l) => norm(l).startsWith(norm(name))) })
  anchors.push({ name: 'connection degree line (1st/2nd/3rd)', ok: top.some((l) => /^(·\s*)?(1st|2nd|3rd\+?)$/i.test(l.trim())) })
  anchors.push({ name: `"${L.contact}" label`, ok: top.some((l) => norm(l) === norm(L.contact)) || !!findLabel(main, L.contact) })
  // LinkedIn renders the current company and the dates as plain text (not links, not li): read the lines.
  const lineCount = (key: string) => regions.find((r) => r.label === key)?.line_count ?? 0
  const dated = (key: string) => (regions.find((r) => r.label === key)?.lines ?? []).filter((l) => /\b(19|20)\d{2}\b|\bPresent\b/.test(l)).length
  anchors.push({ name: 'headline line right after the name (top region)', ok: top.findIndex((l) => norm(l).startsWith(norm(name))) >= 0 && top.length > 2 })
  anchors.push({ name: 'school link anywhere', ok: links.some((l) => l.kind === 'school') })
  anchors.push({ name: 'company link in Experience region', ok: links.some((l) => l.kind === 'company' && l.region === 'experience') })
  anchors.push({ name: 'dated lines in Experience (year or "Present")', ok: dated('experience') > 0, note: `${dated('experience')} of ${lineCount('experience')} lines` })
  anchors.push({ name: 'dated lines in Education', ok: dated('education') > 0, note: `${dated('education')} of ${lineCount('education')} lines` })

  const payload: ProfilePayload = { v: 1, page: 'profile', url: loc.href, slug: ref.id, doc_title: doc.title, name_parsed: name, mode, regions, links }
  return { page: 'profile', anchors, payload }
}

export function extract(doc: Document, loc: Location): Extraction {
  const kind = pageOf(loc.href).kind
  if (kind === 'job') return extractJob(doc, loc)
  if (kind === 'profile') return extractProfile(doc, loc)
  return { page: 'other', anchors: [], payload: null }
}
