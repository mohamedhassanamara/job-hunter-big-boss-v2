import { ArrowRight, CircleCheck, FileText, Globe, Mail } from 'lucide-react'
import { Link } from 'react-router'
import { TrackBadge } from '@/components/app/badges'
import { Section } from '@/components/app/PageHeader'
import { Button } from '@/components/ui/button'
import { apiUrl } from '@/lib/api'
import { useLetterStudio } from '@/lib/queries/letters'
import { METHOD_LABELS, openListingAndCv, shortDate } from '@/lib/tracking'
import type { JobDetail } from '@/lib/types'

const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })

const OUTREACH_NEXT: Record<JobDetail['application']['tracks']['outreach'], string> = {
  no_contact: 'Find who to write to',
  contact: 'Draft the email',
  drafted: 'Review the draft',
  approved: 'Add it to the send queue',
  queued: 'In the send queue',
  sent: 'Sent',
}

/** Both routes at a glance: the web application and the cold email, each with its next step. */
export function TracksSummary({ job }: { job: JobDetail }) {
  const t = job.application.tracks
  const approvedCv = job.cv_versions.some((v) => v.status === 'approved')
  const appNext =
    t.application === 'applied'
      ? `Applied ${t.applied_at ? shortDate(t.applied_at) : ''}${t.web_method ? ` · ${METHOD_LABELS[t.web_method]}` : ''}`
      : approvedCv
        ? 'Open the listing, apply, then mark it applied'
        : 'Approve a CV first'
  return (
    <div data-tour="job-tracks" className="grid grid-cols-2 gap-3 max-md:grid-cols-1">
      <button
        type="button"
        onClick={() => scrollTo('application')}
        className="flex items-start gap-3 rounded-lg border border-border bg-surface p-3 text-left shadow-sm transition-colors duration-120 hover:border-border-strong"
      >
        <Globe className="mt-0.5 size-4 text-fg-subtle" />
        <span className="min-w-0 flex-1 space-y-1">
          <span className="flex items-center justify-between gap-2">
            <span className="text-sm font-semibold">Application</span>
            <TrackBadge kind="application" tracks={t} />
          </span>
          <span className="block truncate text-xs text-fg-muted">{appNext}</span>
        </span>
      </button>
      <button
        type="button"
        onClick={() => scrollTo('outreach')}
        className="flex items-start gap-3 rounded-lg border border-border bg-surface p-3 text-left shadow-sm transition-colors duration-120 hover:border-border-strong"
      >
        <Mail className="mt-0.5 size-4 text-fg-subtle" />
        <span className="min-w-0 flex-1 space-y-1">
          <span className="flex items-center justify-between gap-2">
            <span className="text-sm font-semibold">Outreach</span>
            <TrackBadge kind="outreach" tracks={t} />
          </span>
          <span className="block truncate text-xs text-fg-muted">
            {t.contact_name ? `${t.contact_name} · ` : ''}
            {t.outreach === 'sent' && t.sent_at ? `Sent ${shortDate(t.sent_at)}` : OUTREACH_NEXT[t.outreach]}
          </span>
        </span>
      </button>
    </div>
  )
}

/** The web application: listing + approved CV (+ cover letter) in one click, then Mark applied. */
export function ApplicationSection({ job, onApplied }: { job: JobDetail; onApplied: () => void }) {
  const t = job.application.tracks
  const approved = job.cv_versions.find((v) => v.status === 'approved')
  const show = job.application.stage !== 'new'
  const letters = useLetterStudio(show && approved ? job.application.id : NaN)
  if (!show) return null
  const letter = letters.data?.letters.find((l) => l.status === 'approved' && l.format !== 'form')
  const pdf = approved ? apiUrl(`/cv/${approved.id}/pdf`, { download: true }) : ''
  const letterPdf = letter ? apiUrl(`/letters/${letter.id}/pdf`, { download: true }) : null
  return (
    <Section title="Application" action={<TrackBadge kind="application" tracks={t} />}>
      <div className="p-4 text-sm">
        {t.application === 'applied' ? (
          <p className="flex items-center gap-2">
            <CircleCheck className="size-4 text-success-dot" />
            Applied on the website{t.applied_at ? ` on ${shortDate(t.applied_at)}` : ''}
            {t.web_method ? ` (${METHOD_LABELS[t.web_method]})` : ''}. The CV and letter you sent are locked.
          </p>
        ) : !approved ? (
          <div className="flex items-center gap-3">
            <FileText className="size-4 text-fg-subtle" />
            <span className="flex-1 text-fg-muted">The application uses your approved CV. Approve the CV first.</span>
            <Button size="sm" asChild>
              <Link to={`/jobs/${job.id}/cv`}>Open CV Studio</Link>
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-fg-muted">
              Apply on the company site with your approved CV v{approved.version}
              {letter ? ` and cover letter v${letter.version}` : ''}, then mark it applied: those versions get locked. You can
              email someone there too (Outreach below).
            </p>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={() => openListingAndCv(job.url, pdf, letterPdf)}>
                {letter ? 'Open listing + CV + cover letter' : 'Open listing + CV'}
                <ArrowRight />
              </Button>
              <Button size="sm" variant="ghost" asChild>
                <a href={pdf}>
                  <FileText />
                  Download CV only
                </a>
              </Button>
              <Button size="sm" onClick={onApplied}>
                <CircleCheck />
                Mark applied
              </Button>
            </div>
          </div>
        )}
      </div>
    </Section>
  )
}
