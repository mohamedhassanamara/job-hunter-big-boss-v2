import { api } from '@/lib/api'
import type { InterviewStudio, JobDetail, JobList, PipelineCard, ReadyItem, Today, ToGetQueue } from '@/lib/types'

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
  | 'confirmation'
  | 'cv'
  | 'letter'
  | 'interview'
  | 'glossary'
  | 'listing-flags'
  | 'questions'
  | 'copilot'
  | 'signals'
  | 'contact-check'
  | 'get-contact'
  | 'linkedin'
  | 'linkedin-messages'
  | 'studio'
  | 'email-route'
  | 'outreach'
  | 'contacts'
  | 'experience'
  | 'settings'
  | 'motivation'

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
      { target: 'today-scoring', title: 'Scoring progress', body: 'How many jobs are scored with the current prompt and model, best jobs first, and what is left of the free Gemini quota per key (separate daily quota per key, reset at midnight Pacific). When every key is used up the rest waits and carries on by itself; you can also score it right away with the Ollama cloud model.', placement: 'left' },
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
      { target: 'job-stage', title: 'Stage', body: 'Move the job between stages. The web application and the cold email each have their own track below.' },
      { target: 'job-next', title: 'Always the next step', body: 'The primary button changes with the stage: shortlist, generate CV, draft email, mark applied…' },
      { target: 'job-fit', title: 'Sub-scores and evidence', body: 'Each sub-score has a reason and a quote from the listing; quotes the app cannot find in the text are marked unverified. Low confidence? Fetch or paste the full listing and rescore.', placement: 'right' },
      { target: 'job-contact', title: 'Contact resolution', body: 'Who the email goes to: your best-ranked contact at the company (imported or found by you). Before any email, you verify they are still there; nobody yet means Get contact (Outreach → Contacts to get).', placement: 'left' },
      { target: 'job-timeline', title: 'Timeline', body: 'Every stage change, CV version and email, newest first.', placement: 'left' },
    ],
  },
  confirmation: {
    id: 'confirmation',
    title: 'Second opinion',
    description: 'Ask Claude to double-check a score',
    resolveRoute: async () => {
      const id = await firstJobId()
      return id ? `/jobs/${id}` : '/discover'
    },
    steps: [
      { target: 'job-confirm', title: 'A second opinion, next to the score', body: 'Claude (on your subscription) scores this job again with the same prompt and tells you in plain words whether to apply: seniority, skills, location and visa, language. It is stored next to the main score and never replaces it; both show side by side.', placement: 'right' },
      { target: 'confirm-ask', title: 'Ask Claude', body: 'It takes about 20 to 60 seconds. If Claude is not available it falls back to Gemma through the Gemini API; if that fails too, you can copy the prompt into the Gemini Pro app and paste its answer back.', placement: 'left' },
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
      { target: 'cv-editor', title: 'Only your experience', body: 'Claude picks bullets from your Experience for this job and may lightly adapt their wording (verb, clause order, the listing\'s term for what you did); titles, companies and dates come straight from your data. Every number and skill is checked against the source, and problems are listed at the top.', placement: 'right' },
      { target: 'original-only', title: 'Your words stay yours', body: 'Your Experience text is never changed. An adapted bullet shows its difference from your original with Revert to original, and this switch makes the whole CV use your bullets exactly as written. Adaptations that drop a number, tool or outcome, or change the length by more than 15%, are refused in code.', placement: 'right' },
      { target: 'cv-editor', title: 'Force in, leave out, edit', body: 'The eye toggles a bullet, project or certification. Edit any text inline. The page re-fits in code, without calling Claude again. Every role stays on the CV so your timeline has no gaps.', placement: 'right' },
      { target: 'cv-preview', title: 'The real PDF', body: 'Rendered from a style-only LaTeX template and fitted to exactly one full page: low-value bullets are dropped when it overflows, more are added when it is short.', placement: 'left' },
      { target: 'cv-versions', title: 'Versions and templates', body: 'Regenerate makes a new draft; older versions are kept. With several templates you can switch style per CV.' },
      { target: 'cv-approve', title: 'Approve', body: 'Approving offers the next step: draft the email when there is a contact, otherwise the job moves to Ready to apply. Download uses your filename pattern.' },
    ],
  },
  'listing-flags': {
    id: 'listing-flags',
    title: 'Listing red flags',
    description: 'No pay range, hype wording, a posting that has been up for months',
    resolveRoute: async () => {
      const cards = await api.get<PipelineCard[]>('/applications')
      for (const c of cards.filter((c) => c.stage !== 'closed')) {
        const job = await api.get<JobDetail>(`/jobs/${c.job_id}`)
        if (job.listing_flags?.length) return `/jobs/${c.job_id}`
      }
      return '/pipeline'
    },
    steps: [
      { target: 'listing-flags', title: 'Read in code, no model', body: 'Three hints from the listing itself: no salary or pay range anywhere in the text, hype wording that stands in for the work (rockstar, ninja, "like a family"), and a posting older than 90 days (it may be filled, or an evergreen ad). A truncated listing can never prove a missing salary, so that flag waits for the full description.', placement: 'left' },
      { target: 'listing-flags', title: 'Hints, not verdicts', body: 'They never change the fit score and never hide a job: a missing salary is normal in some countries, and an old ad may still be open. They are there so you ask the right question before you spend an application on it.', placement: 'left' },
    ],
  },
  glossary: {
    id: 'glossary',
    title: 'Glossary',
    description: 'Your own words for moving from mobile to data',
    resolveRoute: async () => '/settings?section=candidate',
    steps: [
      { target: 'settings-glossary', title: 'Your words, nobody else\'s', body: 'Write how your experience says something (left) and the term the field you are moving into uses for it (right). Nothing is suggested or invented: the generators only use a term you wrote.', placement: 'left' },
      { target: 'settings-glossary', title: 'Where it is used', body: 'The CV summary and the cover letters may use the right-hand term only for work whose Experience item contains the left-hand words, in a sentence that cites it. A term adds a name, never a tool, a number or years; the honesty rules still apply and the claim check reads your glossary.', placement: 'left' },
    ],
  },
  interview: {
    id: 'interview',
    title: 'Interview prep',
    description: 'A pitch and STAR stories from your experience, every claim checked',
    resolveRoute: async () => {
      const cards = (await api.get<PipelineCard[]>('/applications')).filter((c) => c.stage !== 'closed' && c.stage !== 'new')
      for (const c of cards) {
        const studio = await api.get<InterviewStudio>(`/applications/${c.application_id}/interview-prep`)
        if (studio.prep) return `/jobs/${c.job_id}/interview`
      }
      return cards[0] ? `/jobs/${cards[0].job_id}/interview` : '/pipeline'
    },
    steps: [
      { target: 'interview-checks', title: 'Checked before you see it', body: 'Every sentence about you cites your Experience and may only say what those items say: tools, numbers and scope as written, your exact years wording, and the honesty rules for project-based tracks. A story whose items state no result simply has none: an outcome is never invented. Errors block approval.', placement: 'bottom' },
      { target: 'interview-pitch', title: 'Tell me about yourself', body: 'Three or four sentences that lead from your current role to this one. Edit any sentence: it autosaves and is re-checked, with no new Claude call.', placement: 'right' },
      { target: 'interview-story', title: 'STAR stories', body: 'Situation, task, action and result, each from a different item of your Experience and chosen for what the listing asks for. The chips show which items every sentence comes from.', placement: 'left' },
      { target: 'interview-questions', title: 'Likely questions', body: 'Taken from this listing, each pointing at the story that answers it best, plus questions you can ask them.', placement: 'right' },
      { target: 'claim-check', title: 'The claim check', body: 'Before you can approve, the Claude claim verifier judges every sentence against your Experience, facts and the listing. A text you edit afterwards must pass again.', placement: 'top' },
      { target: 'interview-approve', title: 'Approve', body: 'Approving marks this version as the one to practise with. Regenerating writes a new draft and keeps the old one superseded.', placement: 'bottom' },
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
  questions: {
    id: 'questions',
    title: 'Application questions',
    description: 'Grounded answers for application forms',
    resolveRoute: async () => {
      const ready = await api.get<ReadyItem[]>('/applications/ready')
      const item = ready.find((r) => r.letter_status !== 'none') ?? ready[0]
      return item ? `/jobs/${item.job_id}` : '/applications?tab=ready'
    },
    steps: [
      { target: 'job-letter', title: 'Cover letter', body: 'Web applications get an optional cover letter, written from the approved CV in the listing’s language. Open the studio to review and approve it.', placement: 'right' },
      { target: 'job-questions', title: 'The form’s questions', body: 'Paste the questions with their character limits. Answers come from your approved CV (or the listing), are checked like the letter, and a limit is never exceeded silently: an answer that is too long is flagged, never cut. They stay saved on the job; copy each one into the form.', placement: 'right' },
    ],
  },
  'email-route': {
    id: 'email-route',
    title: 'Apply and email on the job page',
    description: 'Two tracks: application and outreach',
    resolveRoute: async () => {
      const cards = await api.get<PipelineCard[]>('/applications')
      const card = cards.find((c) => c.tracks.outreach === 'drafted') ?? cards.find((c) => c.tracks.outreach !== 'no_contact' && c.stage !== 'new')
      return card ? `/jobs/${card.job_id}#outreach` : '/pipeline'
    },
    steps: [
      { target: 'job-tracks', title: 'Both routes', body: 'Every job can have a web application and a cold email to someone there. Each track shows its own status and next step; the stage reaches Applied / Emailed with the first one.', placement: 'bottom' },
      { target: 'job-outreach', title: 'Outreach, one step at a time', body: 'First, Get contact: who to look for (by company size) with LinkedIn links, or verify the contact you already have. Then draft the email from your approved CV, review it here (checks, sources, test send), approve, then add it to the send queue, which shows its place and send time. Sent it yourself? Record it: the CV is locked either way.', placement: 'right' },
    ],
  },
  copilot: {
    id: 'copilot',
    title: 'Copilot',
    description: 'Ask anything, answered from your data',
    resolveRoute: async () => '/copilot',
    steps: [
      { target: 'copilot-threads', title: 'Your conversations', body: 'Global chats about your search, with your profile and experience pool as context. Each job also has its own Copilot on its page (the Copilot button, or C).', placement: 'right' },
      { target: 'copilot-messages', title: 'Answers from your data', body: 'The local model (gemma4:12b via Ollama) answers. Numbers or tools that are neither in your experience nor the listing are flagged under the answer; copy any answer with one click.', placement: 'left' },
      { target: 'copilot-input', title: 'It only answers', body: 'Interview prep, CV gaps, a LinkedIn message, a translation… It has no tools: it never changes anything in the app.', placement: 'top' },
    ],
  },
  signals: {
    id: 'signals',
    title: 'Company signals',
    description: 'Verified facts your cold emails open with',
    resolveRoute: async () => {
      const cards = await api.get<PipelineCard[]>('/applications')
      const card = cards.find((c) => c.tracks.outreach !== 'no_contact' && c.stage !== 'new' && c.stage !== 'closed')
      return card ? `/jobs/${card.job_id}` : '/pipeline'
    },
    steps: [
      { target: 'signals-panel', title: 'Researched only when you draft', body: "When you click Draft email with AI (or Research now), the app reads the company's own site and recent news, and a model extracts facts. Each keeps its exact quote, checked in code against the page; a fact without a verified quote is dropped. Fresh signals (30 days) are reused with no new fetch.", placement: 'top' },
      { target: 'signals-panel', title: 'Pick what the email uses', body: 'Ticked signals feed the email hook; the email cites them. Add a fact you know yourself. With no signal, a draft is marked Needs a signal and cannot be approved.', placement: 'top' },
    ],
  },
  linkedin: {
    id: 'linkedin',
    title: 'LinkedIn',
    description: 'Daily searches and one-click import',
    resolveRoute: async () => '/linkedin',
    steps: [
      { target: 'linkedin-searches', title: "Today's searches", body: 'One LinkedIn job search per role and target country, posted in the past 24 hours, newest first. Click one: it opens in a new tab and is marked opened today. You browse; the app never visits LinkedIn.', placement: 'bottom' },
      { target: 'linkedin-bookmark', title: 'One-click import', body: 'Drag “Save to Job Hunter” to your bookmarks bar. On a LinkedIn job page, click it: a small window shows what it read (and how), you check it, save, and the job is scored right away.', placement: 'top' },
    ],
  },
  'linkedin-messages': {
    id: 'linkedin-messages',
    title: 'LinkedIn messages',
    description: 'Who to message about a job, notes and follow-ups',
    resolveRoute: async () => {
      const cards = await api.get<PipelineCard[]>('/applications')
      const card = cards.find((c) => c.stage !== 'new' && c.stage !== 'closed')
      return card ? `/jobs/${card.job_id}#linkedin` : '/pipeline'
    },
    steps: [
      { target: 'linkedin-groups', title: 'Who to message', body: 'In this order: the hiring team (captured with the bookmark), alumni of your school, team leads in your field, then recruiters. Each group has a LinkedIn search link built for this company; you pick people and add them (paste their profile header).', placement: 'bottom' },
      { target: 'linkedin-person', title: 'A note per person', body: 'Claude drafts a connection note within your limit (200 characters on a free account), different for the hiring team, alumni and others. The school angle is for alumni only. You copy it, send it yourself, and mark it sent; the counter tracks your daily requests.', placement: 'top' },
      { target: 'linkedin-person', title: 'After they accept', body: 'Draft the follow-up: one proof from your experience and one direct ask (a referral, or who to talk to). Reminders come up when nobody answers. An email and a LinkedIn request never go to the same person within 3 days.', placement: 'top' },
    ],
  },
  'get-contact': {
    id: 'get-contact',
    title: 'Get contact',
    description: 'Find or verify who to write to, one job at a time',
    resolveRoute: async () => {
      const q = await api.get<ToGetQueue>('/contacts/to-get')
      const item = q.items.find((i) => i.state === 'get') ?? q.items[0]
      return item ? `/outreach?tab=contacts&app=${item.application_id}` : '/outreach?tab=contacts'
    },
    steps: [
      { target: 'contacts-to-get', title: 'Contacts to get', body: 'Every job you moved past New that needs a contact, or a check of the one it has, best fit first. No email is drafted (and no company researched) before its contact is verified.', placement: 'right' },
      { target: 'found-counter', title: 'Your extension limit', body: 'Contacts you found today against the Apollo extension\'s daily limit (Settings → Contacts). It warns near the limit; it never blocks.', placement: 'bottom' },
      { target: 'find-contact', title: 'Find contact: one click', body: 'Looks in the company cache first (a company already looked up costs nothing), then Hunter, Prospeo, Apollo and Apify with your keys, then builds the address from the company\'s email pattern and verifies it. It stops at the first verified email and shows the top 3 by your ranking, each with its source. Catch-all and unverified addresses are never used.', placement: 'left' },
      { target: 'provider-credits', title: 'Credits left this month', body: 'Counted per key and reset monthly, with Apify in dollars. A key a provider refuses is disabled and flagged here and in Settings → Contacts; none is ever pushed past its credits.', placement: 'bottom' },
      { target: 'get-contact', title: 'Who to look for, or verify first', body: 'No contact: the roles to look for at this company (by its size), LinkedIn links and the steps. A contact from a CSV: where it came from, the "may have left" check, then Still there (V), Left or wrong person (L) or Edit (E). A verification lasts 30 days (a setting).', placement: 'left' },
      { target: 'contact-form', title: 'Paste, check, save', body: 'Copy the Apollo extension\'s panel or a LinkedIn header and paste it (P): the fields fill in. Check them, then ⌘↵ saves and moves to the next job. Try Hunter is there when the extension finds nothing, and shows its credits first.', placement: 'left' },
    ],
  },
  'contact-check': {
    id: 'contact-check',
    title: 'Contact still there?',
    description: 'Signs your contact left, before you email them',
    resolveRoute: async () => {
      const cards = await api.get<PipelineCard[]>('/applications')
      for (const c of cards.filter((c) => c.tracks.outreach !== 'no_contact' && c.stage !== 'closed')) {
        const job = await api.get<JobDetail>(`/jobs/${c.job_id}`)
        if (job.contact_alerts.length) return `/jobs/${c.job_id}`
      }
      return '/pipeline'
    },
    steps: [
      { target: 'contact-alert', title: 'Contact may have left', body: "Each time the company is researched, the app searches the news for your contact's name and reads the company's pages. A sentence naming them with a departure (left, dismissed, former CEO) or naming someone new in their role raises this warning, with its source.", placement: 'left' },
      { target: 'contact-alert', title: 'Write to someone else, or verify', body: "The email can't be approved while it shows. Write to the next contact by your ranking in one click, or, once you've checked they're still there, dismiss it (Undo for 8 seconds). A dismissed warning stays dismissed.", placement: 'left' },
    ],
  },
  studio: {
    id: 'studio',
    title: 'Studio',
    description: 'Every CV and cover letter in one place',
    resolveRoute: async () => '/studio',
    steps: [
      { target: 'studio-filters', title: 'Filter by type and status', body: 'CVs, PDF letters and form texts across all jobs: drafts to review, approved ones, and those sent (locked).', placement: 'bottom' },
      { target: 'studio-list', title: 'Open the studio', body: 'J / K to move, Enter opens the CV studio or the letter studio for that job.', placement: 'top' },
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
      { target: 'contacts-companies', title: 'Companies and who to write to', body: 'Every company with jobs, and the person its emails go to. Filter to those with a contact to get or where you found nobody.', placement: 'right' },
      { target: 'contacts-detail', title: 'Ranked by role', body: 'Contacts are ordered by the ranking in Settings → Contacts (CTO, head of engineering or data, engineering manager, tech lead, then HR). Pick another person for a single job; matching never overrides your choice.', placement: 'left' },
      { target: 'contacts-import', title: 'Import your Apollo exports', body: 'Drop several CSVs at once. Contacts are deduplicated by email and by company + name, imported in batches with a progress bar, and the database is backed up first.', route: '/contacts?tab=import' },
      { target: 'contacts-match', title: 'Match report', body: 'How many open jobs have a contact, a contact to get, or nobody, by track and country. Matching also runs after every discovery run and import.', route: '/contacts?tab=match' },
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
  motivation: {
    id: 'motivation',
    title: 'Motivation',
    description: 'Streak, chests, your shop and the Motiv Center',
    resolveRoute: async () => '/',
    steps: [
      { target: 'motivation-badges', title: 'Your streak, always in view', body: 'The flame is your streak of workdays where you reached your daily goal (5 applications by default), with today\'s progress next to it. Weekends carry a running streak by themselves. Today never shows as broken before midnight.', placement: 'bottom' },
      { target: 'today-streak', title: 'The last weeks', body: 'Each square is a day: filled when you reached the goal, outlined on counted weekends. It is computed from your history every time, so undoing an application corrects it.', placement: 'left' },
      { target: 'today-chest', title: 'Chests', body: 'Every 30 applications (Settings → Motivation) unlock a chest with 1 to 10 tokens. Extra applications carry over; tokens are never taken back.', placement: 'left' },
      { target: 'motiv-tabs', route: '/motivation', title: 'Motiv Center', body: 'Small tools for the hard days: a breathing exercise, the 5-minute rule to get started, WOOP planning, your wins from real data, and your own goal images and videos.', placement: 'bottom' },
      { target: 'motiv-shop', route: '/motivation?tab=shop', title: 'Spend your tokens', body: 'Set your own rewards with a token price. Buying asks first and never takes you below zero; tick a purchase once you have taken the treat.', placement: 'top' },
    ],
  },
}

export const TOUR_LIST = Object.values(TOURS)
