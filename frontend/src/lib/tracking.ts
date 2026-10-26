import { trackAction } from './usage'
import type { ApplyMethod, CloseReason, InterviewOutcome, InterviewType, ResponseKind, Stage } from './types'

export const METHOD_LABELS: Record<ApplyMethod, string> = {
  company_site: 'Company site',
  job_board: 'Job board',
  email: 'Email',
  linkedin: 'LinkedIn (Easy Apply or from LinkedIn)',
  other: 'Other',
}

export const RESPONSE_LABELS: Record<ResponseKind, string> = {
  positive: 'Positive reply',
  rejection: 'Rejection',
  other: 'Other reply',
}

export const INTERVIEW_TYPE_LABELS: Record<InterviewType, string> = {
  hr: 'HR / intro',
  technical: 'Technical',
  take_home: 'Take-home',
  final: 'Final',
  other: 'Other',
}

export const OUTCOME_LABELS: Record<InterviewOutcome, string> = {
  pending: 'Pending',
  passed: 'Passed',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

export const CLOSE_REASON_LABELS: Record<CloseReason, string> = {
  rejected: 'Rejected',
  no_response: 'No response',
  withdrawn: 'Withdrew',
  offer_accepted: 'Offer accepted',
  offer_declined: 'Offer declined',
  offer: 'Offer',
  dismissed: 'Not a fit',
}

/** After applying, only real outcomes; before, a job is dismissed or withdrawn. */
export const AFTER_APPLY_REASONS: CloseReason[] = ['rejected', 'no_response', 'withdrawn', 'offer_accepted', 'offer_declined']
export const BEFORE_APPLY_REASONS: CloseReason[] = ['dismissed', 'withdrawn']

export function isApplied(stage: Stage): boolean {
  return stage === 'done' || stage === 'interview'
}

/** Today as YYYY-MM-DD in local time (the value of a date input). */
export function todayIso(): string {
  return localIso(new Date())
}

/** A Date as YYYY-MM-DD in local time. */
export function localIso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** 0.667 → "67%"; null → "—". */
export function pct(rate: number | null | undefined): string {
  return rate === null || rate === undefined ? '—' : `${Math.round(rate * 100)}%`
}

/** "Mon 30 Sep, 10:00" */
export function shortDateTime(iso: string): string {
  return new Date(iso).toLocaleString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

/** "30 Sep 2026" */
export function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

function download(url: string): void {
  const a = document.createElement('a')
  a.href = url
  a.download = ''
  document.body.appendChild(a)
  a.click()
  a.remove()
}

/** "Open listing + CV (+ cover letter)": the listing in a new tab and the approved PDFs
 * downloaded, in one click. Downloads are spaced so the browser doesn't drop the second one. */
export function openListingAndCv(
  listingUrl: string,
  pdfUrl: string,
  letterUrl?: string | null,
  ref?: { kind: 'job' | 'app'; id: number },
): void {
  trackAction('open_listing', ref)
  window.open(listingUrl, '_blank', 'noopener,noreferrer')
  download(pdfUrl)
  if (letterUrl) window.setTimeout(() => download(letterUrl), 400)
}
