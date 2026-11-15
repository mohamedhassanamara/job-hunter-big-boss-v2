/**
 * The "is this profile someone I saved?" answer, as pure functions. No DOM access here (a guard test
 * checks it): the content script passes in `location.pathname`, and the answer comes from the app
 * on this computer through the worker. The lookup only reads; it never saves or changes anything.
 */

export interface LinkedJob {
  job_id: number
  outreach_id: number
  title: string
  company: string
  status: string
  has_first_message: boolean
}

export interface LookupResult {
  matched: boolean
  name: string | null
  jobs: LinkedJob[]
}

export type LookupView =
  | { kind: 'none' }
  | { kind: 'one'; job: LinkedJob }
  | { kind: 'many'; jobs: LinkedJob[] }
  | { kind: 'saved_no_job'; name: string | null }

/** The profile slug from the address path only: `/in/<slug>/…`. "" on any other page. */
export function slugFromPath(pathname: string): string {
  const m = pathname.match(/\/in\/([^/?#]+)/)
  return m ? m[1] : ''
}

/** The app path of the lookup for a slug (the worker only forwards `/ext/*`). */
export const lookupPath = (slug: string): string => `/ext/person/lookup?slug=${encodeURIComponent(slug)}`

/** Which of the four panel states an answer means. A missing answer (no token, app down) is "none". */
export function viewOf(result: LookupResult | null): LookupView {
  if (!result?.matched) return { kind: 'none' }
  if (result.jobs.length === 0) return { kind: 'saved_no_job', name: result.name }
  if (result.jobs.length === 1) return { kind: 'one', job: result.jobs[0] }
  return { kind: 'many', jobs: result.jobs }
}

/** The job page in the app, scrolled to this person's LinkedIn messages (the First message draft). */
export const jobPath = (job: LinkedJob): string => `/jobs/${job.job_id}?person=${job.outreach_id}#linkedin`

const STATUS: Record<string, string> = {
  to_contact: 'to contact',
  sent: 'invite sent',
  accepted: 'accepted',
  messaged: 'messaged',
  replied: 'replied',
}
export const statusLabel = (status: string): string => STATUS[status] ?? status
