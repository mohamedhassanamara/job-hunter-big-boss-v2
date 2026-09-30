import { api } from '@/lib/api'
import type { JobList, PipelineCard, ReadyItem, Today } from '@/lib/types'

/**
 * Guided tours, one per feature. They run in the sandbox workspace (sample data only).
 * `target` matches a `data-tour="…"` attribute; steps without one show a centered card.
 */
export interface TourStep {
  target?: string
  title: string
  body: string
  /** Navigate here (within the sandbox) before showing this step. */
  route?: string
  placement?: 'top' | 'bottom' | 'left' | 'right'
}

export type TourId =
  | 'today'
  | 'discover'
  | 'pipeline'
  | 'applications'
  | 'job'
  | 'cv'
  | 'letter'
  | 'outreach'
  | 'contacts'
  | 'experience'
  | 'settings'

export interface Tour {
  id: TourId
  title: string
  description: string
  resolveRoute: () => Promise<string>
  steps: TourStep[]
}

const firstJobId = async () => {
  const jobs = await api.get<JobList>('/jobs?stage=new&sort=fit')
  return jobs.items[0]?.id
}

export const TOURS: Record<TourId, Tour> = {
  today: {
    id: 'today',
    title: 'Today',
    description: 'Your daily inbox of decisions',
    resolveRoute: async () => '/',
    steps: [
      { target: 'today-greeting', title: 'Your daily inbox', body: 'Today collects everything that needs a decision from you, so you can start here every morning.' },
      { target: 'today-high-fit', title: 'New high-fit jobs', body: 'Fresh jobs above your fit threshold (Settings → Search profile). Click one to open it in Discover.' },
      { target: 'today-review', title: 'CVs and emails to review', body: 'Nothing is final or sent until you approve it. Tailored CVs and drafted emails wait here.' },
      { target: 'today-manual', title: 'Manual applications', body: 'Jobs without a contact go to web apply: open the listing with the approved CV, then mark it applied.', placement: 'top' },
      { target: 'today-followups', title: 'Follow-ups', body: 'No reply 7 and 14 days after applying? A follow-up shows here; snooze or dismiss it. After 30 days the app suggests closing as no response, but only your click closes anything.', placement: 'top' },
      { target: 'today-interviews', title: 'Upcoming interviews', body: 'Interview rounds scheduled in the next 14 days.', placement: 'left' },
      { target: 'today-queue', title: 'Send queue', body: 'Approved emails go out one at a time, 15 minutes apart, at most 20 per queue. Pause anytime.', placement: 'left' },
      { target: 'today-discovery', title: 'Discovery status', body: 'Discovery runs daily on its own. If a source fails, you see it here, not buried in logs.', placement: 'left' },
    ],
  },
  discover: {
    id: 'discover',
    title: 'Discover',
    description: 'Triage newly found jobs',
    resolveRoute: async () => {
      const id = await firstJobId()
      return id ? `/discover?job=${id}` : '/discover'
    },
    steps: [
      { target: 'discover-tabs', title: 'Your triage inbox', body: 'New holds every job discovery found that you have not triaged yet. All open and All widen the view.' },
      { target: 'discover-filters', title: 'Filter and sort', body: 'Narrow by source, remote type, country, fit or age. Filters live in the URL, so a view can be bookmarked.' },
      { target: 'discover-list', title: 'Fit score first', body: 'Each row shows the fit score (0–100), company, location and source. Cross-source duplicates and companies you already contacted are flagged.', placement: 'right' },
      { target: 'discover-panel', title: 'Details without leaving the list', body: 'Everything about the job without leaving the list. J / K move between jobs.', placement: 'left' },
      { target: 'discover-fit', title: 'Scored, with evidence', body: 'Your local model rates role, skills, seniority, location and languages, quoting the listing for each. The 0–100 score is computed in code, and disqualifying flags (like no visa sponsorship) cap it.', placement: 'left' },
      { target: 'discover-label', title: 'Label to train the scorer', body: 'Mark jobs Good, Maybe or No with 1 / 2 / 3. Labels are separate from the pipeline, and `make eval` measures how well scores agree with them.', placement: 'left' },
      { target: 'discover-hide-scores', title: 'Label blind', body: 'Hide scores while you label so the scorer\'s opinion doesn\'t sway yours. The list switches to newest first and fit filters turn off.', placement: 'bottom' },
      { target: 'discover-actions', title: 'Shortlist or dismiss', body: 'S shortlists, D dismisses, and both can be undone from the toast. Shortlisted jobs move to your Pipeline.', placement: 'left' },
    ],
  },
  pipeline: {
    id: 'pipeline',
    title: 'Pipeline',
    description: 'Every opportunity by stage',
    resolveRoute: async () => '/pipeline',
    steps: [
      { target: 'pipeline-board', title: 'Every opportunity, by stage', body: 'New → Shortlisted → CV ready → Ready to send / apply → Sent / Applied → Interview → Closed.', placement: 'top' },
      { target: 'pipeline-column-cv_ready', title: 'Drag to move', body: 'Drag a card to another column. Only allowed moves are accepted. Applied and Interview open a short form (date, method, CV sent; round), and closing asks for a reason.', placement: 'right' },
      { target: 'pipeline-view', title: 'Board or table', body: 'The table sorts by fit, stage or time in stage and supports J / K, S and D.', placement: 'left' },
      { target: 'pipeline-dismissed', title: 'Dismissed stays out of the way', body: 'Dismissed jobs are hidden from Closed unless you switch this on.' },
    ],
  },
  applications: {
    id: 'applications',
    title: 'Applications',
    description: 'Apply, follow up, see what works',
    resolveRoute: async () => '/applications',
    steps: [
      { target: 'applications-tabs', title: 'After the CV', body: 'Ready to apply, everything you applied to, and the numbers. Nothing here calls a model.' },
      { target: 'applications-open', title: 'One click to apply', body: 'Opens the listing in a new tab and downloads the approved CV, named with your filename pattern. O does the same from the keyboard.', placement: 'left' },
      { target: 'applications-mark', title: 'Mark applied', body: 'Record the date, how you applied and notes. The CV version you sent is locked: later edits always create a new version.', placement: 'left' },
      { target: 'applications-list', title: 'Everything you applied to', body: 'J / K to move, Enter opens the job. The side panel shows the timeline plus Log reply, Log interview and Close….', route: '/applications?tab=applied', placement: 'top' },
      { target: 'applications-filters', title: 'Filter and export', body: 'Filter by track, country, source, stage and date. Export CSV gives one row per application with the same filters.' },
      { target: 'applications-weekly', title: 'Stats', body: 'Applications per week, response and interview rates by track, country and source (with counts, so small numbers aren\'t misread), and the median days to a first answer.', route: '/applications?tab=stats', placement: 'bottom' },
    ],
  },
  job: {
    id: 'job',
    title: 'Job detail',
    description: 'One place per opportunity',
    resolveRoute: async () => {
      const cards = await api.get<PipelineCard[]>('/applications')
      const card = cards.find((c) => c.stage === 'cv_ready') ?? cards[0]
      return card ? `/jobs/${card.job_id}` : '/pipeline'
    },
    steps: [
      { target: 'job-header', title: 'One place per opportunity', body: 'Listing, fit, contact, CV, email, notes and timeline for a single job.' },
      { target: 'job-stage', title: 'Stage and route', body: 'Move the job between stages, and choose cold email (needs a contact) or web apply.' },
      { target: 'job-next', title: 'Always the next step', body: 'The primary button changes with the stage: shortlist, generate CV, draft email, mark applied…' },
      { target: 'job-fit', title: 'Sub-scores and evidence', body: 'Each sub-score has a reason and a quote from the listing; quotes the app cannot find in the text are marked unverified. Low confidence? Fetch or paste the full listing and rescore.', placement: 'right' },
      { target: 'job-contact', title: 'Contact resolution', body: 'Tier 1: your Apollo import. Tier 2: a queued manual Apollo lookup. Tier 3: no contact → web apply.', placement: 'left' },
      { target: 'job-timeline', title: 'Timeline', body: 'Every stage change, CV version and email, newest first.', placement: 'left' },
    ],
  },
  cv: {
    id: 'cv',
    title: 'CV Studio',
    description: 'Review and edit tailored CVs',
    resolveRoute: async () => {
      const today = await api.get<Today>('/today')
      const item = today.cvs_to_review[0]
      return item ? `/jobs/${item.job_id}/cv` : '/pipeline'
    },
    steps: [
      { target: 'cv-editor', title: 'Only your experience', body: 'Claude picks and rewords bullets from your Experience for this job; titles, companies and dates come straight from your data. Every number and skill is checked against the source, and problems are listed at the top.', placement: 'right' },
      { target: 'cv-editor', title: 'Force in, leave out, edit', body: 'The eye toggles a bullet, project or certification. Edit any text inline. The page re-fits in code, without calling Claude again. Every role stays on the CV so your timeline has no gaps.', placement: 'right' },
      { target: 'cv-preview', title: 'The real PDF', body: 'Rendered from a style-only LaTeX template and fitted to exactly one full page: low-value bullets are dropped when it overflows, more are added when it is short.', placement: 'left' },
      { target: 'cv-versions', title: 'Versions and templates', body: 'Regenerate makes a new draft; older versions are kept. With several templates you can switch style per CV.' },
      { target: 'cv-approve', title: 'Approve', body: 'Approving offers the next step: draft the email when there is a contact, otherwise the job moves to Ready to apply. Download uses your filename pattern.' },
    ],
  },
  letter: {
    id: 'letter',
    title: 'Cover letter',
    description: 'A grounded lettre de motivation for web applications',
    resolveRoute: async () => {
      const ready = await api.get<ReadyItem[]>('/applications/ready')
      const item = ready.find((r) => r.letter_status !== 'none') ?? ready[0]
      return item ? `/jobs/${item.job_id}/letter` : '/applications?tab=ready'
    },
    steps: [
      { target: 'letter-language', title: "The listing's language", body: 'French listing, French letter (English otherwise). Pick another language for this job if you prefer; the next letter is written in it.', placement: 'bottom' },
      { target: 'letter-checks', title: 'Checked before you see it', body: 'Every sentence comes from your approved CV or the listing. The opening names the company and something from the listing; 2-3 concrete builds; one ask at the end; the word range; no banned phrases (French and English lists); your exact years wording. Errors block approval.', placement: 'right' },
      { target: 'letter-editor', title: 'Edit freely', body: 'Paragraphs autosave, are re-checked and the PDF re-renders, with no new Claude call. Header, date, salutation, closing formula and signature come from your settings.', placement: 'right' },
      { target: 'letter-preview', title: 'Same look as your CV', body: 'Rendered from the CV template with the same header, on one page.', placement: 'left' },
      { target: 'letter-approve', title: 'Approve, then apply', body: 'The approved letter joins the CV in Ready to apply: one click opens the listing and downloads both. Copy as text fills a form field instead. Mark applied locks the versions you sent.' },
    ],
  },
  outreach: {
    id: 'outreach',
    title: 'Outreach',
    description: 'Review emails and the send queue',
    resolveRoute: async () => '/outreach',
    steps: [
      { target: 'outreach-list', title: 'Every email is reviewed', body: 'Drafted cold emails wait here, one per job (never in bulk). J / K to move, A to approve, R to reject.', placement: 'right' },
      { target: 'outreach-checks', title: 'Checked before you see it', body: 'Every sentence must come from your approved CV (or the listing), with one ask, the right first name and company, no banned phrases, under the word limit. Problems block approval; near-copies of other emails are flagged.', placement: 'left' },
      { target: 'outreach-editor', title: 'Edit freely', body: 'Edits autosave and are re-checked. Your signature and a polite opt-out line are added when it is sent, and the approved CV is attached.', placement: 'left' },
      { target: 'outreach-test-send', title: 'Test on yourself first', body: 'Sends this exact email, CV attached, to your own address with a [TEST] subject. The queue cannot start before one test went through.', placement: 'top' },
      { target: 'outreach-approve', title: 'Approve, then add to the queue', body: 'Approve marks the email Ready to send; Add to send queue is a separate step that shows its place and send time. Nothing is sent before that.', placement: 'top' },
      { target: 'outreach-queue', title: 'Send queue', body: 'One email every 15 minutes, at most 20 per queue, pause anytime. It survives restarts; an email caught mid-send is never resent blindly. A sent email moves the job to Sent and starts the follow-up reminders.', route: '/outreach?tab=queue' },
    ],
  },
  contacts: {
    id: 'contacts',
    title: 'Contacts',
    description: 'Who each job is written to',
    resolveRoute: async () => '/contacts',
    steps: [
      { target: 'contacts-companies', title: 'Companies and who to write to', body: 'Every company with jobs, and the person its emails go to. Filter to those that still need a lookup or where nobody was found.', placement: 'right' },
      { target: 'contacts-detail', title: 'Ranked by role', body: 'Contacts are ordered by the ranking in Settings → Contacts (CTO, head of engineering or data, engineering manager, tech lead, then HR). Pick another person for a single job; matching never overrides your choice.', placement: 'left' },
      { target: 'contacts-lookups', title: 'Manual Apollo lookups', body: 'Companies with jobs but no imported contact, best fit first. Look one up with the Apollo extension, then enter who you found (E) or mark nobody (N): that job then goes to web apply.', route: '/contacts?tab=lookups', placement: 'top' },
      { target: 'contacts-lookup-counter', title: 'Daily cap', body: 'The extension has a free daily quota; the counter resets at midnight. The cap is a setting.', route: '/contacts?tab=lookups' },
      { target: 'contacts-import', title: 'Import your Apollo exports', body: 'Drop several CSVs at once. Contacts are deduplicated by email and by company + name, imported in batches with a progress bar, and the database is backed up first.', route: '/contacts?tab=import' },
      { target: 'contacts-match', title: 'Match report', body: 'How many open jobs have a contact, wait on a lookup, or have nobody, by track and country. Matching also runs after every discovery run and import.', route: '/contacts?tab=match' },
    ],
  },
  experience: {
    id: 'experience',
    title: 'Experience',
    description: 'Your master experience',
    resolveRoute: async () => '/experience',
    steps: [
      { target: 'experience-groups', title: 'Your master experience', body: 'The single source for every tailored CV and every fit score: roles, projects, skills, education.', placement: 'top' },
      { target: 'experience-tags', title: 'Tags', body: 'Tags power filtering here and let the CV generator match your experience to each job.' },
      { target: 'experience-row', title: 'Edit, reorder, include', body: 'Click to edit, drag to reorder. The switch excludes an item from CVs without deleting it.' },
      { target: 'experience-add', title: 'Add items', body: 'Add roles, projects, volunteering, skills, education and certifications with concrete, quantified bullets.', placement: 'left' },
    ],
  },
  settings: {
    id: 'settings',
    title: 'Settings',
    description: 'Profile, sources and schedule',
    resolveRoute: async () => '/settings',
    steps: [
      { target: 'settings-card', title: 'Search profile', body: 'Roles, countries, remote preference and max age drive discovery. Title exclusions filter noise, and seniority is never filtered unless you add it.', placement: 'left' },
      { target: 'settings-tracks', title: 'Roles & tracks', body: 'Group the job titles you want into tracks (Data/AI, Mobile…) with your years in each. Sources search every title in French, Spanish, German, Italian and Dutch too, and the scorer judges role and seniority against the track a job matched.', placement: 'left' },
      { target: 'settings-card', title: 'Sources', body: 'Each source shows its last run, counts and errors, plus a Test button (dry run) and a filter report for tuning. Company job boards takes a list of employers you can extend: pick their job-board platform and paste the id from their careers URL.', route: '/settings?section=sources', placement: 'left' },
      { target: 'settings-cv-emphasis', title: 'CV per track', body: 'Choose which skill groups and tags lead the CV for each track (Data/AI, Mobile…), and how downloads are named.', route: '/settings?section=cv', placement: 'left' },
      { target: 'settings-templates', title: 'CV templates', body: 'Templates are style only. Add your own (.tex.j2 + config); it must compile to one page with sample data before you can pick it.', route: '/settings?section=templates', placement: 'left' },
      { target: 'settings-contacts-ranking', title: 'Who to write to', body: 'Order the role groups: the first group with someone at the company gets the email. Saving re-ranks every contact and re-matches open jobs.', route: '/settings?section=contacts', placement: 'left' },
      { target: 'settings-card', title: 'Daily schedule', body: 'Discovery runs automatically at this time every day. The Run discovery button works anytime.', route: '/settings?section=schedule', placement: 'left' },
    ],
  },
}

export const TOUR_LIST = Object.values(TOURS)
