/**
 * The LinkedIn bookmark (bookmarklet). `capturePage` runs on the LinkedIn job page you're
 * viewing, in your browser only: it reads the page and nothing else (no request to LinkedIn, no
 * clicking, no scrolling). It must stay self-contained (no imports, no outer variables) because
 * its source text becomes the bookmark.
 *
 * Each field is tried with several strategies, and the one that worked is recorded:
 * json-ld (the JobPosting block) → page (LinkedIn's layout, several known variants, then
 * headings) → meta (og:title / <title>) → url (the job id).
 *
 * The data reaches the app in the import window's URL fragment (never sent to any server), so
 * LinkedIn's Content Security Policy (connect-src) doesn't apply; postMessage is a second channel.
 */

export interface PageCapture {
  v: number
  url: string
  job_id: string
  title: string
  company: string
  company_url: string
  location: string
  workplace: string
  description: string
  poster: { name: string; title: string; url: string } | null
  sources: Record<string, string>
  captured_at: string
  page_title: string
}

export function capturePage(doc: Document, loc: Location): PageCapture {
  const out: PageCapture = {
    v: 1,
    url: loc.href,
    job_id: '',
    title: '',
    company: '',
    company_url: '',
    location: '',
    workplace: '',
    description: '',
    poster: null,
    sources: {},
    captured_at: new Date().toISOString(),
    page_title: doc.title,
  }
  type Field = 'job_id' | 'title' | 'company' | 'company_url' | 'location' | 'workplace' | 'description'
  const set = (k: Field, v: unknown, how: string) => {
    const value = typeof v === 'string' ? v.replace(/\s+\n/g, '\n').trim() : ''
    if (!out[k] && value) {
      out[k] = value
      out.sources[k] = how
    }
  }
  const text = (el: Element | null): string => (el ? ((el as HTMLElement).innerText || el.textContent || '').trim() : '')
  const first = (selectors: string[], root: ParentNode = doc): Element | null => {
    for (const sel of selectors) {
      try {
        const el = root.querySelector(sel)
        if (el && text(el)) return el
      } catch {
        /* an unsupported selector: try the next */
      }
    }
    return null
  }
  // HTML → text without innerHTML (LinkedIn enforces Trusted Types).
  const strip = (html: string): string =>
    html
      // JSON-LD descriptions are often HTML escaped once more: unescape the tags first.
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/<\s*br\s*\/?>/gi, '\n')
      .replace(/<\/(p|div|li|h[1-6]|ul|ol)>/gi, '\n')
      .replace(/<li[^>]*>/gi, '• ')
      .replace(/<[^>]+>/g, '')
      .replace(/&nbsp;/g, ' ')
      .replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&#39;|&apos;/g, "'")
      .replace(/&quot;/g, '"')
      .replace(/\n{3,}/g, '\n\n')

  // The job id: /jobs/view/<id>/ or ?currentJobId=<id> (search results).
  const idMatch = loc.href.match(/\/jobs\/view\/(?:[^/?#]*?-)?(\d{6,})/) || loc.href.match(/[?&](?:currentJobId|jobId)=(\d{6,})/)
  if (idMatch) set('job_id', idMatch[1], 'url')

  // 1. JSON-LD (the public job page carries a JobPosting block).
  doc.querySelectorAll('script[type="application/ld+json"]').forEach((node) => {
    try {
      const parsed = JSON.parse(node.textContent || '')
      const list = Array.isArray(parsed) ? parsed : parsed['@graph'] || [parsed]
      for (const x of list) {
        if (!x || x['@type'] !== 'JobPosting') continue
        set('title', x.title, 'json-ld')
        const org = x.hiringOrganization || {}
        set('company', org.name, 'json-ld')
        if (typeof org.sameAs === 'string' && org.sameAs.includes('/company/')) set('company_url', org.sameAs, 'json-ld')
        const place = [].concat(x.jobLocation || [])[0] as { address?: Record<string, string> } | undefined
        const a = (place && place.address) || {}
        set('location', [a.addressLocality, a.addressRegion, a.addressCountry].filter(Boolean).join(', '), 'json-ld')
        if (x.jobLocationType === 'TELECOMMUTE') set('workplace', 'Remote', 'json-ld')
        if (typeof x.description === 'string') set('description', strip(x.description), 'json-ld')
      }
    } catch {
      /* not JSON: ignore */
    }
  })

  // 2. The page layout (signed-in job view and search pane, then the public page), then headings.
  const pane = first(['.jobs-search__job-details--container', '.job-view-layout', '.jobs-details', '.scaffold-layout__detail', 'main']) || doc.body
  const titleEl = first(
    [
      '.job-details-jobs-unified-top-card__job-title h1',
      '.job-details-jobs-unified-top-card__job-title',
      '.jobs-unified-top-card__job-title',
      'h1.top-card-layout__title',
      '.top-card-layout__title',
      'h1',
    ],
    pane,
  )
  set('title', text(titleEl).split('\n')[0], 'page')
  const card =
    first(['.job-details-jobs-unified-top-card__container--two-pane', '.job-details-jobs-unified-top-card', '.jobs-unified-top-card', '.top-card-layout'], pane) ||
    (titleEl && titleEl.closest('section, div[class*="top-card"], div[class*="topcard"]')) ||
    (titleEl && titleEl.parentElement && titleEl.parentElement.parentElement) ||
    pane
  const companyEl =
    first(
      [
        '.job-details-jobs-unified-top-card__company-name a',
        '.job-details-jobs-unified-top-card__company-name',
        '.jobs-unified-top-card__company-name a',
        '.topcard__org-name-link',
        '.top-card-layout__second-subline a',
      ],
      card,
    ) || card.querySelector('a[href*="/company/"]')
  set('company', text(companyEl).split('\n')[0], 'page')
  const companyLink = (companyEl && companyEl.closest('a')) || card.querySelector('a[href*="/company/"]')
  if (companyLink) set('company_url', (companyLink as HTMLAnchorElement).href, 'page')
  const metaLine = first(
    [
      '.job-details-jobs-unified-top-card__primary-description-container',
      '.job-details-jobs-unified-top-card__tertiary-description-container',
      '.job-details-jobs-unified-top-card__bullet',
      '.jobs-unified-top-card__bullet',
      '.topcard__flavor--bullet',
    ],
    card,
  )
  set('location', text(metaLine).split(/\s·\s|\n/)[0], 'page')
  const workplace = text(card).match(/\b(Remote|Hybrid|On-site|À distance|Télétravail|Hybride|Sur site|Presencial|Híbrido|En remoto)\b/i)
  if (workplace) set('workplace', workplace[1], 'page')
  const desc = first(
    [
      '#job-details',
      '.jobs-description__content .jobs-box__html-content',
      '.jobs-description-content__text',
      '.jobs-description__container',
      '.show-more-less-html__markup',
      '.description__text',
    ],
    pane,
  )
  set('description', text(desc), 'page')
  if (!out.description) {
    // "About the job" heading → its section's text.
    const heading = Array.from(pane.querySelectorAll('h2, h3')).find((h) => /about the job|à propos de l.offre|acerca del empleo|informazioni sull.offerta|über den job/i.test(text(h)))
    const section = heading && (heading.closest('section, article') || heading.parentElement)
    if (section) set('description', text(section).replace(text(heading), ''), 'page')
  }

  // The hiring team / job poster, when LinkedIn shows it.
  const teamHeading = Array.from(pane.querySelectorAll('h2, h3, span, strong')).find((h) =>
    /^(meet the hiring team|rencontrez l.équipe de recrutement|job poster|conoce al equipo de contratación)/i.test(text(h)),
  )
  const team = first(['.hirer-card__hirer-information', '.job-details-people-who-can-help__section--two-pane', '.jobs-poster'], pane) || (teamHeading && (teamHeading.closest('section, div.artdeco-card') || teamHeading.parentElement))
  const person = team && (team.querySelector('a[href*="/in/"]') as HTMLAnchorElement | null)
  if (team && person) {
    const lines = text(team)
      .split('\n')
      .map((x) => x.trim())
      .filter((x) => x && !/^(meet the hiring team|message|job poster|·|\d(st|nd|rd|th))$/i.test(x) && !/^rencontrez/i.test(x))
    const name = (text(person.querySelector('strong, span[aria-hidden="true"]')) || text(person) || lines[0] || '').split('\n')[0]
    const idx = lines.findIndex((x) => x === name)
    const role = idx >= 0 ? lines.slice(idx + 1).find((x) => !/^(·|\d+(st|nd|rd|th)|job poster|you)$/i.test(x) && x !== name) : ''
    if (name) out.poster = { name, title: role || '', url: person.href.split('?')[0] }
  }

  // 3. Meta tags: og:title "Company hiring Title in Location | LinkedIn", <title> "Title | Company | LinkedIn".
  const og = (doc.querySelector('meta[property="og:title"]') as HTMLMetaElement | null)?.content || ''
  const hiring = og.match(/^(.+?) hiring (.+?) in (.+?)(?: \| LinkedIn)?$/)
  if (hiring) {
    set('company', hiring[1], 'meta')
    set('title', hiring[2], 'meta')
    set('location', hiring[3], 'meta')
  }
  const parts = doc.title.replace(/^\(\d+\)\s*/, '').split(' | ')
  if (parts.length >= 3 && /linkedin/i.test(parts[parts.length - 1])) {
    set('title', parts[0], 'meta')
    set('company', parts[1], 'meta')
  }
  const ogDesc = (doc.querySelector('meta[name="description"], meta[property="og:description"]') as HTMLMetaElement | null)?.content
  if (ogDesc && ogDesc.length > 200) set('description', ogDesc, 'meta')
  return out
}
