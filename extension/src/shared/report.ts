/** The text that leaves the page when you press Copy: redacted by default (text shown only for known UI labels). */
import { labels } from './labels'
import type { Extraction, LinkItem, Region } from './extract'
import { norm } from './text'

const KNOWN = (): Set<string> => {
  const L = labels()
  const words = [L.jobAbout, L.jobTeam, L.contact, ...Object.values(L.sections), 'Message', 'Connect', 'Follow', 'More', 'Save', 'Apply', 'Easy Apply', 'Remote', 'Hybrid', 'On-site', 'Show all', 'Show more', 'See more', 'Present', 'Hiring', 'Open to', 'Premium', 'Pending', '·', '1st', '2nd', '3rd', '3rd+']
  return new Set(words.map(norm))
}

const redactLine = (line: string, known: Set<string>, includeText: boolean): string => (includeText || known.has(norm(line)) ? line : `<${line.length} chars>`)

function region(r: Region, known: Set<string>, includeText: boolean): Region {
  return { ...r, lines: r.lines.map((l) => redactLine(l, known, includeText)) }
}
function links(items: LinkItem[], known: Set<string>, includeText: boolean): LinkItem[] {
  return items.map((l) => ({ ...l, text: redactLine(l.text, known, includeText) }))
}

export function buildReport(x: Extraction, includeText: boolean): string {
  const known = KNOWN()
  const p = x.payload
  let payload: unknown = null
  if (p?.page === 'job') {
    payload = {
      ...p,
      url: includeText ? p.url : p.url.replace(/\d{6,}/g, '<n>').replace(/\?.*$/, ''),
      doc_title: includeText ? p.doc_title : p.doc_title.replace(/[^|]+/g, (m) => `<${m.trim().length}>`),
      title_parsed: includeText ? p.title_parsed : `<${p.title_parsed.length} chars>`,
      company_parsed: includeText ? p.company_parsed : `<${p.company_parsed.length} chars>`,
      header: region(p.header, known, includeText),
      about: region(p.about, known, includeText),
      team: region(p.team, known, includeText),
      links: links(p.links, known, includeText),
    }
  } else if (p?.page === 'profile') {
    payload = {
      ...p,
      url: includeText ? p.url : p.url.replace(/\/in\/[^/?#]+/, '/in/<slug>').replace(/\?.*$/, ''),
      slug: includeText ? p.slug : '<slug>',
      doc_title: includeText ? p.doc_title : p.doc_title.replace(/[^|]+/g, (m) => `<${m.trim().length}>`),
      name_parsed: includeText ? p.name_parsed : `<${p.name_parsed.length} chars>`,
      regions: p.regions.map((r) => region(r, known, includeText)),
      links: links(p.links, known, includeText),
    }
  }
  return JSON.stringify({ tool: 'jh-extractor', version: 1, includeText, page: x.page, anchors: x.anchors, payload }, null, 1)
}
