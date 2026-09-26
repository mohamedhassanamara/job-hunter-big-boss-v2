import {
  ArrowLeft,
  ArrowRight,
  ChevronDown,
  CircleCheck,
  FileText,
  Globe,
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
  type Tone,
} from '@/components/app/badges'
import { CloseDialog } from '@/components/app/CloseDialog'
import { ContactCard, ExternalListingButton, FitCard, JobFlags } from '@/components/app/job-cards'
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
import { SegmentedList, SegmentedTrigger, Tabs } from '@/components/ui/tabs'
import { Tooltip } from '@/components/ui/tooltip'
import { useTriageActions } from '@/hooks/useTriageActions'
import { ApiError } from '@/lib/api'
import { absoluteDate, relativeTime, STAGE_LABELS } from '@/lib/format'
import { useJob, usePatchApplication } from '@/lib/queries/jobs'
import { useGenerateDraft } from '@/lib/queries/workflow'
import type { CloseReason, DraftStatus, JobDetail, Route, Stage } from '@/lib/types'
import { Timeline } from './Timeline'

const DRAFT_TONE: Record<DraftStatus, Tone> = {
  draft: 'amber',
  approved: 'blue',
  queued: 'blue',
  sent: 'green',
  rejected: 'gray',
  failed: 'red',
}
const DRAFT_LABEL: Record<DraftStatus, string> = {
  draft: 'Needs review',
  approved: 'Approved',
  queued: 'Queued',
  sent: 'Sent',
  rejected: 'Rejected',
  failed: 'Failed',
}

function stageMenuLabel(stage: Stage, route: Route) {
  if (stage === 'ready') return route === 'web_apply' ? 'Ready to apply' : 'Ready to send'
  if (stage === 'done') return route === 'web_apply' ? 'Applied' : 'Sent'
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

function EmailSection({ job }: { job: JobDetail }) {
  const generate = useGenerateDraft()
  const navigate = useNavigate()
  const draft = job.drafts.find((d) => d.status !== 'rejected') ?? job.drafts[0]
  const hasApprovedCV = job.cv_versions.some((v) => v.status === 'approved')

  if (job.application.route === 'web_apply') return null

  const onGenerate = () =>
    generate.mutate(job.application.id, {
      onSuccess: (d) => {
        toast.success('Email draft created', { description: `To ${d.contact?.full_name}` })
        navigate(`/outreach?draft=${d.id}`)
      },
      onError: (e) => toast.error(e.message),
    })

  return (
    <Section
      title="Cold email"
      action={
        draft && (
          <Button size="xs" variant="ghost" asChild>
            <Link to={`/outreach?draft=${draft.id}${draft.status === 'draft' ? '' : '&status=all'}`}>
              Open in Outreach
              <ArrowRight />
            </Link>
          </Button>
        )
      }
    >
      {!draft ? (
        <EmptyState
          compact
          icon={Mail}
          title="No email drafted"
          description={
            !job.contact
              ? 'This job needs a contact before an email can be drafted.'
              : hasApprovedCV
                ? `Draft a short email to ${job.contact.full_name}.`
                : 'Approve the CV first; the email references it.'
          }
          action={
            job.contact &&
            hasApprovedCV && (
              <Button size="sm" onClick={onGenerate} disabled={generate.isPending}>
                <Sparkles />
                Draft email
              </Button>
            )
          }
        />
      ) : (
        <div className="space-y-2 p-4">
          <div className="flex items-center gap-2">
            <ToneBadge tone={DRAFT_TONE[draft.status]}>{DRAFT_LABEL[draft.status]}</ToneBadge>
            {draft.contact_name && <span className="text-xs text-fg-muted">To {draft.contact_name}</span>}
            <span className="ml-auto text-xs text-fg-subtle">{relativeTime(draft.updated_at)}</span>
          </div>
          <p className="text-sm font-medium">{draft.subject}</p>
          <p className="line-clamp-4 text-sm whitespace-pre-line text-fg-muted">{draft.body}</p>
        </div>
      )}
    </Section>
  )
}

function WebApplyCallout({ job, onApplied }: { job: JobDetail; onApplied: () => void }) {
  if (job.application.route !== 'web_apply' || job.application.stage !== 'ready') return null
  return (
    <div className="rounded-lg border border-tone-blue-border bg-info-bg p-4">
      <div className="flex items-start gap-3">
        <Globe className="mt-0.5 size-4 text-info-fg" />
        <div className="flex-1 space-y-1">
          <p className="text-sm font-semibold text-info-fg">Apply on the company site</p>
          <p className="text-sm text-fg-muted">
            No contact was found, so this one is a manual application. Open the listing, attach your
            approved CV, and mark it applied when you're done.
          </p>
          <div className="flex flex-wrap gap-2 pt-2">
            <Button size="sm" asChild>
              <a href={job.url} target="_blank" rel="noreferrer">
                Open listing
                <ArrowRight />
              </a>
            </Button>
            <Tooltip content="PDF rendering arrives with the LaTeX slice (mock in phase 0)">
              <span>
                <Button size="sm" disabled>
                  <FileText />
                  Download CV (PDF)
                </Button>
              </span>
            </Tooltip>
            <Button size="sm" variant="default" onClick={onApplied}>
              <CircleCheck />
              Mark applied
            </Button>
          </div>
        </div>
      </div>
    </div>
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
  const generateDraft = useGenerateDraft()
  const [closing, setClosing] = useState(false)

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
  const setRoute = (route: Route) =>
    patch.mutate(
      { id: app.id, patch: { route } },
      {
        onSuccess: () =>
          toast.success(route === 'web_apply' ? 'Route set to web apply' : 'Route set to cold email'),
        onError: (e) => toast.error(e.message),
      },
    )
  const target = { jobId: job.id, title: job.title, company: job.company.name }
  const latestCV = job.cv_versions[0]
  const openDraft = job.drafts.find((d) => d.status === 'draft')

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
  } else if (app.stage === 'cv_ready' && app.route === 'web_apply') {
    primary = (
      <Button variant="default" onClick={() => setStage('ready')}>
        <Globe />
        Mark ready to apply
      </Button>
    )
  } else if (app.stage === 'cv_ready') {
    primary = openDraft ? (
      <Button variant="default" asChild>
        <Link to={`/outreach?draft=${openDraft.id}`}>
          <Mail />
          Review email draft
        </Link>
      </Button>
    ) : (
      <Button
        variant="default"
        disabled={!job.contact || generateDraft.isPending}
        onClick={() =>
          generateDraft.mutate(app.id, {
            onSuccess: (d) => navigate(`/outreach?draft=${d.id}`),
            onError: (e) => toast.error(e.message),
          })
        }
      >
        <Sparkles />
        Draft email
      </Button>
    )
  } else if (app.stage === 'ready' && app.route === 'web_apply') {
    primary = (
      <Button variant="default" onClick={() => setStage('done', undefined, 'Marked as applied')}>
        <CircleCheck />
        Mark applied
      </Button>
    )
  } else if (app.stage === 'ready') {
    primary = (
      <Button variant="default" asChild>
        <Link to="/outreach?tab=queue">
          <Mail />
          View send queue
        </Link>
      </Button>
    )
  } else if (app.stage === 'done') {
    primary = (
      <Button variant="default" onClick={() => setStage('interview', undefined, 'Interview logged')}>
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

      <header className="flex items-start justify-between gap-6 border-b border-border pb-5">
        <div className="min-w-0 space-y-2">
          <h1 className="text-xl font-semibold tracking-tight">{job.title}</h1>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Link to={`/contacts?company=${job.company.id}`} className="font-medium hover:underline">
              {job.company.name}
            </Link>
            <span className="text-fg-subtle">·</span>
            <LocationText location={job.location} />
            <RemoteBadge remote={job.remote_type} />
            <SourceBadge source={job.source} short={false} />
            <span className="text-xs text-fg-subtle">
              Posted {relativeTime(job.posted_at)}
              {job.salary_text && ` · ${job.salary_text}`}
            </span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="secondary" aria-label="Change stage" className="pl-2">
                <StageBadge stage={app.stage} label={app.stage_label} />
                <ChevronDown className="size-3.5! text-fg-subtle" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>Move to</DropdownMenuLabel>
              {job.allowed_stages.map((s) => (
                <DropdownMenuItem
                  key={s}
                  onSelect={() => (s === 'closed' ? setClosing(true) : setStage(s))}
                >
                  <StageDot stage={s} />
                  {s === 'closed' ? 'Close…' : stageMenuLabel(s, app.route)}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          {app.stage !== 'new' && app.stage !== 'closed' && (
            <Tabs value={app.route === 'undecided' ? '' : app.route} onValueChange={(v) => setRoute(v as Route)}>
              <SegmentedList>
                <Tooltip content={job.contact ? 'Send a cold email' : 'Needs a contact first'}>
                  <span>
                    <SegmentedTrigger value="cold_email" disabled={!job.contact}>
                      <Mail />
                      Email
                    </SegmentedTrigger>
                  </span>
                </Tooltip>
                <SegmentedTrigger value="web_apply">
                  <Globe />
                  Web apply
                </SegmentedTrigger>
              </SegmentedList>
            </Tabs>
          )}
          {primary}
        </div>
      </header>

      <div className="mt-6 grid grid-cols-[minmax(0,1fr)_320px] gap-6 max-lg:grid-cols-1">
        <div className="space-y-4">
          <JobFlags job={job} />
          <WebApplyCallout job={job} onApplied={() => setStage('done', undefined, 'Marked as applied')} />
          <FitCard fit={job.fit_detail} />
          <CVSection job={job} />
          <EmailSection job={job} />
          <NotesCard key={job.id} job={job} />
          <Section title="Listing" action={<ExternalListingButton url={job.url} label="Original" />}>
            <div className="p-4">
              <Prose text={job.description} />
            </div>
          </Section>
        </div>

        <aside className="space-y-4">
          <ContactCard job={job} />
          <div className="rounded-lg border border-border bg-surface p-4">
            <p className="mb-2 text-xs font-medium text-fg-subtle">Company</p>
            <p className="text-sm font-medium">{job.company.name}</p>
            <p className="text-sm text-fg-muted">
              {job.company.contacted_at
                ? `Contacted ${relativeTime(job.company.contacted_at)}`
                : 'Not contacted yet'}
            </p>
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
          <Timeline events={job.events} />
        </aside>
      </div>

      <CloseDialog
        open={closing}
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
