import {
  ArrowLeft,
  ArrowRight,
  BotMessageSquare,
  ChevronDown,
  CircleCheck,
  FileText,
  Mail,
  RotateCcw,
  SearchX,
  Sparkles,
  Star,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import {
  LocationText,
  RemoteBadge,
  SourceBadge,
  StageBadge,
  StageDot,
  ToneBadge,

} from '@/components/app/badges'
import { CloseDialog } from '@/components/app/CloseDialog'
import { LogInterviewDialog, MarkAppliedDialog } from '@/components/app/tracking/TrackingDialogs'
import { AppliedFacts, TrackingActions } from '@/components/app/tracking/TrackingPanel'
import { ConfirmationPanel } from '@/components/app/ConfirmationPanel'
import { FitCard } from '@/components/app/FitCard'
import { AgencyLine, ContactCard, ExternalListingButton, JobFlags } from '@/components/app/job-cards'
import { Section } from '@/components/app/PageHeader'
import { Prose } from '@/components/app/Prose'
import { EmptyState, ErrorState } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Textarea } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip } from '@/components/ui/tooltip'
import { useHotkeys } from '@/hooks/useHotkeys'
import { useTriageActions } from '@/hooks/useTriageActions'
import { ApiError } from '@/lib/api'
import { absoluteDate, relativeTime, SOURCE_LABELS, STAGE_LABELS } from '@/lib/format'
import { useJob, usePatchApplication } from '@/lib/queries/jobs'
import { isApplied } from '@/lib/tracking'
import type { CloseReason, JobDetail, Stage } from '@/lib/types'
import { ApplicationSection, CompanyReasonField, TracksSummary } from './ApplicationSection'
import { CopilotSheet } from './CopilotSheet'
import { LinkedInTrackSection } from '@/components/app/linkedin/LinkedInTrackSection'
import { SignalsPanel } from '@/components/app/research/SignalsPanel'
import { CoverLetterSection } from './CoverLetterSection'
import { InterviewPrepSection } from './InterviewPrepSection'
import { OutreachSection } from './OutreachSection'
import { QuestionsSection } from './QuestionsSection'
import { Timeline } from './Timeline'

function stageMenuLabel(stage: Stage) {
  if (stage === 'done') return 'Applied / emailed'
  return STAGE_LABELS[stage]
}

function NotesCard({ job }: { job: JobDetail }) {
  const patch = usePatchApplication()
  const [value, setValue] = useState(job.notes)
  const [state, setState] = useState<'idle' | 'saving' | 'saved'>('idle')
  const timer = useRef<number | undefined>(undefined)
  const appId = job.application.id

  useEffect(() => () => window.clearTimeout(timer.current), [])

  const onChange = (next: string) => {
    setValue(next)
    setState('saving')
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => {
      patch.mutate(
        { id: appId, patch: { notes: next } },
        {
          onSuccess: () => setState('saved'),
          onError: (e) => {
            setState('idle')
            toast.error(`Couldn't save notes: ${e.message}`)
          },
        },
      )
    }, 700)
  }

  return (
    <Section
      title="Notes"
      action={
        <span className="text-xs text-fg-subtle">
          {state === 'saving' ? 'Saving…' : state === 'saved' ? 'Saved' : 'Autosaves as you type'}
        </span>
      }
    >
      <div className="p-3">
        <Textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Interview notes, referral details, salary expectations…"
          className="min-h-28 border-transparent bg-transparent hover:border-transparent focus-visible:border-primary"
        />
      </div>
    </Section>
  )
}

function CVSection({ job }: { job: JobDetail }) {
  const latest = job.cv_versions[0]
  const canGenerate = job.application.stage !== 'new' && job.application.stage !== 'closed'
  return (
    <Section
      title="Tailored CV"
      action={
        latest && (
          <Button size="xs" variant="ghost" asChild>
            <Link to={`/jobs/${job.id}/cv`}>
              Open CV Studio
              <ArrowRight />
            </Link>
          </Button>
        )
      }
    >
      {job.cv_versions.length === 0 ? (
        <EmptyState
          compact
          icon={FileText}
          title="No CV for this job yet"
          description={
            canGenerate
              ? 'Generate a one-page CV tailored to this listing from your master experience.'
              : 'Shortlist the job first, then generate a tailored CV.'
          }
          action={
            canGenerate && (
              <Button size="sm" asChild>
                <Link to={`/jobs/${job.id}/cv?generate=1`}>
                  <Sparkles />
                  Generate CV
                </Link>
              </Button>
            )
          }
        />
      ) : (
        <ul>
          {job.cv_versions.map((v) => (
            <li key={v.id} className="flex items-center gap-3 border-b border-border px-4 py-2.5 last:border-b-0">
              <FileText className="size-4 text-fg-subtle" />
              <span className="text-sm font-medium">v{v.version}</span>
              <ToneBadge
                tone={v.status === 'approved' ? 'green' : v.status === 'draft' ? 'amber' : 'gray'}
              >
                {v.status === 'approved' ? 'Approved' : v.status === 'draft' ? 'Needs review' : 'Superseded'}
              </ToneBadge>
              {v.locked && <ToneBadge tone="blue">Sent</ToneBadge>}
              {v.page_count === 1 && <span className="text-xs text-fg-subtle">1 page</span>}
              <span className="ml-auto text-xs text-fg-subtle">
                <Tooltip content={absoluteDate(v.created_at)}>
                  <span>{relativeTime(v.created_at)}</span>
                </Tooltip>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Section>
  )
}

function TrackingSection({ job }: { job: JobDetail }) {
  const t = job.tracking
  if (!t) return null
  const target = { appId: job.application.id, title: job.title, company: job.company.name }
  return (
    <Section
      title="Replies and interviews"
      action={
        <TrackingActions target={target} stage={job.application.stage} rounds={t.interviews.length} primary="none" />
      }
    >
      <AppliedFacts tracking={t} />
    </Section>
  )
}

function JobSkeleton() {
  return (
    <div className="mx-auto max-w-6xl space-y-6 px-6 py-6">
      <Skeleton className="h-4 w-24" />
      <div className="space-y-2">
        <Skeleton className="h-7 w-96" />
        <Skeleton className="h-4 w-64" />
      </div>
      <div className="grid grid-cols-[1fr_320px] gap-6">
        <div className="space-y-4">
          <Skeleton className="h-44" />
          <Skeleton className="h-32" />
        </div>
        <div className="space-y-4">
          <Skeleton className="h-36" />
          <Skeleton className="h-64" />
        </div>
      </div>
    </div>
  )
}

export default function JobPage() {
  const { id } = useParams()
  const jobId = Number(id)
  const navigate = useNavigate()
  const { data: job, isPending, error, refetch } = useJob(jobId)
  const patch = usePatchApplication()
  const triage = useTriageActions()
  const [closing, setClosing] = useState(false)
  const [applying, setApplying] = useState(false)
  const [interviewing, setInterviewing] = useState(false)
  const [copilotOpen, setCopilotOpen] = useState(false)
  useHotkeys({ c: () => setCopilotOpen(true) }, { enabled: !!job })

  if (isPending) return <JobSkeleton />
  if (error) {
    if (error instanceof ApiError && error.status === 404) {
      return (
        <EmptyState
          icon={SearchX}
          title="This job doesn't exist"
          description="It may have been removed, or the link is wrong."
          action={
            <Button asChild size="sm" variant="default">
              <Link to="/discover">Back to Discover</Link>
            </Button>
          }
        />
      )
    }
    return <ErrorState error={error} onRetry={() => refetch()} />
  }

  const app = job.application
  const setStage = (stage: Stage, close_reason?: CloseReason, success?: string) =>
    patch.mutate(
      { id: app.id, patch: { stage, close_reason } },
      {
        onSuccess: (c) => toast.success(success ?? `Moved to ${c.stage_label}`, { description: job.title }),
        onError: (e) => toast.error(e.message),
      },
    )
  const target = { jobId: job.id, title: job.title, company: job.company.name }
  const latestCV = job.cv_versions[0]
  const approvedCV = job.cv_versions.find((v) => v.status === 'approved')
  const tracks = app.tracks
  const toOutreach = () => document.getElementById('outreach')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  const pickStage = (s: Stage) => {
    if (s === 'closed') setClosing(true)
    else if (s === 'done' && tracks.application === 'ready') setApplying(true)
    else if (s === 'interview') setInterviewing(true)
    else if (s === 'ready' || s === 'done') toOutreach()
    else setStage(s)
  }
  const emailPending = tracks.outreach !== 'sent'
  const emailLabel: Record<typeof tracks.outreach, string> = {
    no_contact: 'Get contact',
    verify: 'Verify contact',
    contact: 'Draft email',
    drafted: 'Review email',
    approved: 'Add to send queue',
    queued: 'Send queue',
    sent: 'Email sent',
  }

  // The single primary action for this stage.
  let primary: React.ReactNode = null
  if (app.stage === 'new') {
    primary = (
      <Button variant="default" onClick={() => triage.shortlist(target)}>
        <Star />
        Shortlist
      </Button>
    )
  } else if (app.stage === 'shortlisted') {
    primary = (
      <Button variant="default" asChild>
        <Link to={`/jobs/${job.id}/cv${latestCV ? '' : '?generate=1'}`}>
          <Sparkles />
          {latestCV ? 'Review CV' : 'Generate CV'}
        </Link>
      </Button>
    )
  } else if ((app.stage === 'cv_ready' || app.stage === 'ready' || app.stage === 'done') && tracks.application === 'ready') {
    // Both routes: the application first (one click), the email card has its own next step.
    primary = (
      <Button variant="default" onClick={() => setApplying(true)} disabled={!approvedCV}>
        <CircleCheck />
        Mark applied
      </Button>
    )
  } else if ((app.stage === 'cv_ready' || app.stage === 'ready' || app.stage === 'done') && emailPending) {
    primary = (
      <Button variant="default" onClick={toOutreach}>
        <Mail />
        {emailLabel[tracks.outreach]}
      </Button>
    )
  } else if (app.stage === 'done') {
    primary = (
      <Button variant="default" onClick={() => setInterviewing(true)}>
        Log interview
      </Button>
    )
  } else if (app.stage === 'interview') {
    primary = (
      <Button variant="default" onClick={() => setClosing(true)}>
        Record outcome
      </Button>
    )
  } else if (app.stage === 'closed') {
    primary = (
      <Button variant="default" onClick={() => setStage('new', undefined, 'Reopened')}>
        <RotateCcw />
        Reopen
      </Button>
    )
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-5">
      <button
        onClick={() => (window.history.length > 1 ? navigate(-1) : navigate('/discover'))}
        className="mb-3 inline-flex items-center gap-1 text-sm text-fg-muted hover:text-fg"
      >
        <ArrowLeft className="size-4" />
        Back
      </button>

      <header data-tour="job-header" className="flex items-start justify-between gap-6 border-b border-border pb-5">
        <div className="min-w-0 space-y-2">
          <h1 className="text-xl font-semibold tracking-tight">{job.title}</h1>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Link to={`/contacts?company=${job.company.id}`} className="font-medium hover:underline">
              {job.company.name}
            </Link>
            <span className="text-fg-subtle">·</span>
            <LocationText location={job.location} />
            <RemoteBadge remote={job.remote_type} />
            {job.sources && job.sources.length > 1 ? (
              job.sources.map((src) => (
                <SourceBadge key={src} source={src} short={false} />
              ))
            ) : (
              <SourceBadge source={job.source} short={false} />
            )}
            <span className="text-xs text-fg-subtle">
              Posted {relativeTime(job.posted_at)}
              {job.salary_text && ` · ${job.salary_text}`}
            </span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="secondary" aria-label="Change stage" className="pl-2" data-tour="job-stage">
                <StageBadge stage={app.stage} label={app.stage_label} />
                <ChevronDown className="size-3.5! text-fg-subtle" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>Move to</DropdownMenuLabel>
              {job.allowed_stages.map((s) => (
                <DropdownMenuItem
                  key={s}
                  onSelect={() => pickStage(s)}
                >
                  <StageDot stage={s} />
                  {s === 'closed' ? 'Close…' : stageMenuLabel(s)}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          <Tooltip content="Ask about this job (C)">
            <Button variant="secondary" onClick={() => setCopilotOpen(true)} data-tour="job-copilot-open">
              <BotMessageSquare />
              Copilot
            </Button>
          </Tooltip>
          <span data-tour="job-next">{primary}</span>
        </div>
      </header>

      <div className="mt-6 grid grid-cols-[minmax(0,1fr)_320px] gap-6 max-lg:grid-cols-1">
        <div className="space-y-4">
          <JobFlags job={job} />
          {app.stage !== 'new' && <TracksSummary job={job} />}
          {app.stage !== 'new' && app.stage !== 'closed' && <CompanyReasonField key={`reason-${job.id}`} job={job} />}
          <div id="application" className="scroll-mt-4">
            <ApplicationSection job={job} onApplied={() => setApplying(true)} />
          </div>
          <div id="outreach" className="scroll-mt-4">
            <OutreachSection job={job} />
          </div>
          <div id="linkedin" className="scroll-mt-4">
            <LinkedInTrackSection job={job} />
          </div>
          {app.stage !== 'new' && app.stage !== 'closed' && (
            <Section title={`Signals about ${job.company.name}`}>
              <div className="p-4">
                <SignalsPanel
                  companyId={job.company.id}
                  researchBlocked={job.contact_state === 'ready' ? undefined : 'Research waits for a verified contact (Get contact)'}
                />
              </div>
            </Section>
          )}
          <TrackingSection job={job} />
          <div data-tour="job-fit">
            <FitCard job={job} />
          </div>
          <ConfirmationPanel job={job} />
          <CVSection job={job} />
          <CoverLetterSection job={job} />
          <InterviewPrepSection job={job} />
          <QuestionsSection job={job} />
          <NotesCard key={`notes-${job.id}`} job={job} />
          <Section
            title="Listing"
            action={
              job.source_urls && Object.keys(job.source_urls).length > 1 ? (
                <div className="flex flex-wrap items-center gap-1.5">
                  {Object.entries(job.source_urls).map(([src, url]) => (
                    <ExternalListingButton
                      key={src}
                      url={url}
                      label={`View on ${SOURCE_LABELS[src as keyof typeof SOURCE_LABELS] || src}`}
                    />
                  ))}
                </div>
              ) : (
                <ExternalListingButton url={job.url} label={`View on ${SOURCE_LABELS[job.source]}`} />
              )
            }
          >
            <div className="p-4">
              <Prose text={job.description} />
            </div>
          </Section>
        </div>

        <aside className="space-y-4">
          <div data-tour="job-contact">
            <ContactCard job={job} />
          </div>
          <div className="rounded-lg border border-border bg-surface p-4">
            <p className="mb-2 text-xs font-medium text-fg-subtle">Company</p>
            <p className="text-sm font-medium">{job.company.name}</p>
            <p className="text-sm text-fg-muted">
              {job.company.contacted_at
                ? `Contacted ${relativeTime(job.company.contacted_at)}`
                : 'Not contacted yet'}
            </p>
            <AgencyLine job={job} />
            {job.other_jobs_at_company.length > 0 && (
              <div className="mt-3 space-y-1">
                <p className="text-xs text-fg-subtle">Other jobs here</p>
                {job.other_jobs_at_company.map((o) => (
                  <Link
                    key={o.id}
                    to={`/jobs/${o.id}`}
                    className="-mx-2 flex items-center gap-2 rounded-md px-2 py-1 text-sm hover:bg-surface-hover"
                  >
                    <StageDot stage={o.stage} />
                    <span className="flex-1 truncate">{o.title}</span>
                    <span className="text-xs text-fg-subtle">{o.stage_label}</span>
                  </Link>
                ))}
              </div>
            )}
          </div>
          <div data-tour="job-timeline">
            <Timeline events={job.events} />
          </div>
        </aside>
      </div>

      <CopilotSheet job={job} open={copilotOpen} onOpenChange={setCopilotOpen} />
      <MarkAppliedDialog
        key={`apply-${applying}`}
        target={applying ? { appId: app.id, title: job.title, company: job.company.name } : null}
        cvVersion={approvedCV?.version ?? null}
        cvVersionId={approvedCV?.id}
        defaultMethod={job.source === 'linkedin' ? 'linkedin' : 'company_site'}
        onOpenChange={setApplying}
      />
      <LogInterviewDialog
        key={`interview-${interviewing}`}
        target={interviewing ? { appId: app.id, title: job.title, company: job.company.name } : null}
        round={(job.tracking?.interviews.length ?? 0) + 1}
        onOpenChange={setInterviewing}
      />
      <CloseDialog
        key={`close-${closing}`}
        open={closing}
        applied={isApplied(app.stage)}
        title={`${job.title} · ${job.company.name}`}
        onCancel={() => setClosing(false)}
        onConfirm={(reason) => {
          setClosing(false)
          setStage('closed', reason, reason === 'dismissed' ? 'Dismissed' : 'Application closed')
        }}
      />
    </div>
  )
}
