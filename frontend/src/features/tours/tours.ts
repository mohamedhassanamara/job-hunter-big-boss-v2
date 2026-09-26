import { api } from '@/lib/api'
import type { JobList, PipelineCard, Today } from '@/lib/types'

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
  | 'job'
  | 'cv'
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
      { target: 'today-manual', title: 'Manual applications', body: 'Jobs without a contact go to web apply: open the listing, attach the CV, then mark it applied.', placement: 'top' },
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
      { target: 'discover-panel', title: 'Details without leaving the list', body: 'Strengths, gaps, contact status and the full description. J / K move between jobs.', placement: 'left' },
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
      { target: 'pipeline-column-cv_ready', title: 'Drag to move', body: 'Drag a card to another column. Only allowed moves are accepted, and closing asks for a reason.', placement: 'right' },
      { target: 'pipeline-view', title: 'Board or table', body: 'The table sorts by fit, stage or time in stage and supports J / K, S and D.', placement: 'left' },
      { target: 'pipeline-dismissed', title: 'Dismissed stays out of the way', body: 'Dismissed jobs are hidden from Closed unless you switch this on.' },
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
      { target: 'job-fit', title: 'Why it fits', body: 'Strengths and gaps from the fit scorer, so you know how to pitch yourself.', placement: 'right' },
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
      { target: 'cv-editor', title: 'Structured, editable content', body: 'Every section is editable: reorder entries and bullets, and trim what does not fit this job. Drafts autosave.', placement: 'right' },
      { target: 'cv-preview', title: 'One universal template', body: 'Every CV uses the same LaTeX template and is always exactly one page.', placement: 'left' },
      { target: 'cv-fit', title: 'Page-fit check', body: 'Warns about overflow or too much white space. Overflow blocks approval.', placement: 'bottom' },
      { target: 'cv-versions', title: 'Versions', body: 'Regenerate creates a new draft, and older versions are kept for reference.' },
      { target: 'cv-approve', title: 'Approve', body: 'Approving moves the job to CV ready and offers the next step: draft the email, or apply on the web.' },
    ],
  },
  outreach: {
    id: 'outreach',
    title: 'Outreach',
    description: 'Review emails and the send queue',
    resolveRoute: async () => '/outreach',
    steps: [
      { target: 'outreach-list', title: 'Every email is reviewed', body: 'Drafted cold emails wait here. J / K to move, A to approve, R to reject.', placement: 'right' },
      { target: 'outreach-editor', title: 'Edit freely', body: 'Subject and body autosave, and the approved CV is attached automatically.', placement: 'left' },
      { target: 'outreach-approve', title: 'Approve & queue', body: 'Approved emails join the send queue. Nothing is sent before that.', placement: 'top' },
      { target: 'outreach-queue', title: 'Send queue', body: 'One email every 15 minutes, at most 20 per queue. Pause or resume anytime, and remove an item to send it back to review.', route: '/outreach?tab=queue' },
    ],
  },
  contacts: {
    id: 'contacts',
    title: 'Contacts',
    description: 'Apollo contacts and lookups',
    resolveRoute: async () => '/contacts',
    steps: [
      { target: 'contacts-companies', title: 'Contacts by company', body: 'Everything from your Apollo import, grouped by company. A contact at a company routes its jobs to a cold email.', placement: 'right' },
      { target: 'contacts-detail', title: 'Who to email', body: 'Titles, emails and where each contact came from: Apollo import or a manual lookup.', placement: 'left' },
      { target: 'contacts-tabs', title: 'Lookups and imports', body: 'The lookup queue lists jobs waiting for a manual Apollo lookup (daily cap). Import CSV loads a new Apollo export.' },
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
      { target: 'experience-add', title: 'Add items', body: 'Add roles, projects, skills, education and certifications with concrete, quantified bullets.', placement: 'left' },
    ],
  },
  settings: {
    id: 'settings',
    title: 'Settings',
    description: 'Profile, sources and schedule',
    resolveRoute: async () => '/settings',
    steps: [
      { target: 'settings-card', title: 'Search profile', body: 'Roles, countries, remote preference and max age drive discovery. Title exclusions filter noise, and seniority is never filtered unless you add it.', placement: 'left' },
      { target: 'settings-card', title: 'Sources', body: 'Each source shows its last run, counts and errors, plus a Test button (dry run) and a filter report for tuning.', route: '/settings?section=sources', placement: 'left' },
      { target: 'settings-card', title: 'Daily schedule', body: 'Discovery runs automatically at this time every day. The Run discovery button works anytime.', route: '/settings?section=schedule', placement: 'left' },
    ],
  },
}

export const TOUR_LIST = Object.values(TOURS)
