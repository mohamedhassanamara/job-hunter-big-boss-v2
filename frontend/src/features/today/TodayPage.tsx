import {
  ArrowRight,
  CalendarClock,
  CircleCheck,
  Compass,
  FileText,
  Globe,
  Layers,
  type LucideIcon,
  Mail,
  Pause,
  Play,
  Radar,
  Send,
  TriangleAlert,
  Users,
} from 'lucide-react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { FitBadge, SourceBadge, ToneBadge } from '@/components/app/badges'
import { EmptyState, ErrorState } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip } from '@/components/ui/tooltip'
import { useDiscoveryAction } from '@/hooks/useDiscoveryAction'
import { absoluteDate, clockTime, pluralize, relativeTime, shortAge, SOURCE_LABELS } from '@/lib/format'
import { usePatchApplication } from '@/lib/queries/jobs'
import { useQueueControl, useToday } from '@/lib/queries/workflow'
import type { Today } from '@/lib/types'
import { cn } from '@/lib/utils'

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 19 ? 'Good afternoon' : 'Good evening'
}

function Card({
  icon: Icon,
  title,
  count,
  href,
  hrefLabel = 'View all',
  children,
  className,
}: {
  icon: LucideIcon
  title: string
  count?: number
  href?: string
  hrefLabel?: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <section className={cn('flex flex-col rounded-lg border border-border bg-surface shadow-sm', className)}>
      <div className="flex h-11 items-center gap-2 border-b border-border px-4">
        <Icon className="size-4 text-fg-subtle" strokeWidth={1.75} />
        <h2 className="text-sm font-semibold">{title}</h2>
        {count !== undefined && count > 0 && (
          <span className="rounded-sm bg-primary-subtle px-1.5 text-2xs font-semibold text-primary tabular-nums">
            {count}
          </span>
        )}
        {href && (
          <Link
            to={href}
            className="ml-auto inline-flex items-center gap-1 text-xs font-medium text-fg-muted hover:text-fg"
          >
            {hrefLabel}
            <ArrowRight className="size-3.5" />
          </Link>
        )}
      </div>
      <div className="flex-1">{children}</div>
    </section>
  )
}

function Nothing({ text }: { text: string }) {
  return (
    <div className="flex h-full min-h-20 items-center justify-center gap-2 px-4 py-6 text-sm text-fg-subtle">
      <CircleCheck className="size-4 text-success-dot" />
      {text}
    </div>
  )
}

function RowLink({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <Link
      to={to}
      className="flex items-center gap-3 border-b border-border px-4 py-2.5 transition-colors duration-120 last:border-b-0 hover:bg-surface-hover"
    >
      {children}
    </Link>
  )
}

function TitleBlock({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="min-w-0 flex-1">
      <p className="truncate text-sm font-medium">{title}</p>
      <p className="truncate text-xs text-fg-muted">{subtitle}</p>
    </div>
  )
}

function QueueCard({ queue }: { queue: Today['queue'] }) {
  const control = useQueueControl()
  const running = queue.status === 'running'
  const toggle = () =>
    control.mutate(running ? 'pause' : 'resume', {
      onSuccess: (q) =>
        toast.success(q.status === 'running' ? 'Send queue resumed' : 'Send queue paused', {
          description:
            q.status === 'running'
              ? `Next email in ${q.interval_minutes} min (mock: nothing is sent in phase 0)`
              : undefined,
        }),
      onError: (e) => toast.error(e.message),
    })
  return (
    <Card icon={Send} title="Send queue" href="/outreach?tab=queue" hrefLabel="Open">
      <div className="space-y-3 p-4">
        <div className="flex items-center justify-between">
          <ToneBadge tone={running ? 'green' : queue.status === 'paused' ? 'amber' : 'gray'}>
            {running ? 'Running' : queue.status === 'paused' ? 'Paused' : 'Idle'}
          </ToneBadge>
          {queue.pending > 0 && (
            <Button size="sm" onClick={toggle} disabled={control.isPending}>
              {running ? <Pause /> : <Play />}
              {running ? 'Pause' : 'Resume'}
            </Button>
          )}
        </div>
        <dl className="grid grid-cols-2 gap-3">
          <div>
            <dt className="text-xs text-fg-subtle">Pending</dt>
            <dd className="text-xl font-semibold tabular-nums">{queue.pending}</dd>
          </div>
          <div>
            <dt className="text-xs text-fg-subtle">Next send</dt>
            <dd className="text-xl font-semibold tabular-nums">
              {running && queue.next_send_at ? clockTime(queue.next_send_at) : '—'}
            </dd>
          </div>
        </dl>
        <p className="text-xs text-fg-subtle">
          {queue.pending === 0
            ? 'Approved emails land here.'
            : `${queue.interval_minutes} min between sends · ${pluralize(queue.sent, 'email')} sent so far`}
        </p>
      </div>
    </Card>
  )
}

function DiscoveryCard({ runs }: { runs: Today['last_runs'] }) {
  const discovery = useDiscoveryAction()
  const last = runs.reduce<string | null>(
    (acc, r) => (!acc || (r.finished_at ?? r.started_at) > acc ? (r.finished_at ?? r.started_at) : acc),
    null,
  )
  return (
    <Card icon={Radar} title="Last discovery">
      <div className="p-4">
        {runs.length === 0 ? (
          <p className="text-sm text-fg-muted">Discovery hasn't run yet.</p>
        ) : (
          <>
            <p className="mb-3 text-xs text-fg-subtle">
              <Tooltip content={absoluteDate(last)}>
                <span>Finished {relativeTime(last)}</span>
              </Tooltip>
            </p>
            <ul className="space-y-2">
              {runs.map((r) => (
                <li key={r.id} className="flex items-center gap-2 text-sm">
                  <span className="flex-1 truncate">{SOURCE_LABELS[r.source]}</span>
                  {r.status === 'partial' || r.status === 'failed' ? (
                    <Tooltip content={r.error}>
                      <span className="inline-flex items-center gap-1 text-xs text-warning-fg">
                        <TriangleAlert className="size-3.5" />
                        {r.status === 'failed' ? 'Failed' : 'Partial'}
                      </span>
                    </Tooltip>
                  ) : null}
                  <span className="w-16 text-right text-xs text-fg-muted tabular-nums">
                    {r.new_count} new
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
        <Button size="sm" className="mt-4 w-full" onClick={discovery.trigger} disabled={discovery.pending}>
          <Radar />
          Run discovery now
        </Button>
      </div>
    </Card>
  )
}

function TodaySkeleton() {
  return (
    <div className="mx-auto max-w-6xl space-y-6 px-6 py-6">
      <div className="space-y-2">
        <Skeleton className="h-7 w-64" />
        <Skeleton className="h-4 w-48" />
      </div>
      <div className="grid grid-cols-3 gap-4">
        <div className="col-span-2 space-y-4">
          <Skeleton className="h-64" />
          <div className="grid grid-cols-2 gap-4">
            <Skeleton className="h-40" />
            <Skeleton className="h-40" />
          </div>
        </div>
        <div className="space-y-4">
          <Skeleton className="h-52" />
          <Skeleton className="h-52" />
        </div>
      </div>
    </div>
  )
}

function Onboarding() {
  const discovery = useDiscoveryAction()
  const steps = [
    { n: 1, title: 'Add your master experience', text: 'Roles, projects, skills. Every CV and fit score is built from it.' },
    { n: 2, title: 'Import your Apollo contacts', text: 'Jobs at companies with a contact get a cold email instead of a web application.' },
    { n: 3, title: 'Run discovery', text: 'Pulls matching jobs from your sources and scores them. After that, it runs daily.' },
  ]
  return (
    <div className="rounded-lg border border-border bg-surface p-6 shadow-sm">
      <p className="text-md font-semibold tracking-tight">Set up your job hunt</p>
      <p className="text-sm text-fg-muted">Three steps, then this page becomes your daily inbox.</p>
      <ol className="mt-5 grid grid-cols-3 gap-4 max-lg:grid-cols-1">
        {steps.map((s) => (
          <li key={s.n} className="rounded-lg border border-border bg-bg-subtle p-4">
            <span className="flex size-6 items-center justify-center rounded-full bg-primary-subtle text-xs font-semibold text-primary">
              {s.n}
            </span>
            <p className="mt-3 text-sm font-medium">{s.title}</p>
            <p className="mt-1 text-sm text-fg-muted">{s.text}</p>
          </li>
        ))}
      </ol>
      <div className="mt-5 flex gap-2">
        <Button variant="default" size="sm" asChild>
          <Link to="/experience?new=1">
            <Layers />
            Add experience
          </Link>
        </Button>
        <Button size="sm" asChild>
          <Link to="/contacts?tab=import">
            <Users />
            Import contacts
          </Link>
        </Button>
        <Button size="sm" onClick={discovery.trigger} disabled={discovery.pending}>
          <Radar />
          Run discovery
        </Button>
      </div>
    </div>
  )
}

export default function TodayPage() {
  const { data, isPending, error, refetch } = useToday()
  const patch = usePatchApplication()

  if (isPending) return <TodaySkeleton />
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />

  const attention =
    data.new_high_fit_total +
    data.cvs_to_review.length +
    data.drafts_to_approve.length +
    data.ready_to_apply.length
  const date = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })

  const markApplied = (appId: number, title: string) =>
    patch.mutate(
      { id: appId, patch: { stage: 'done' } },
      {
        onSuccess: () => toast.success('Marked as applied', { description: title }),
        onError: (e) => toast.error(e.message),
      },
    )

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-6 py-6">
      <header>
        <h1 className="text-xl font-semibold tracking-tight">{greeting()}</h1>
        <p className="text-sm text-fg-muted">
          {date} ·{' '}
          {data.last_runs.length === 0
            ? "Let's get you set up."
            : attention === 0
              ? "You're all caught up."
              : `${pluralize(attention, 'thing needs', 'things need')} your attention.`}
        </p>
      </header>

      {data.last_runs.length === 0 ? (
        <Onboarding />
      ) : attention === 0 && (
        <div className="rounded-lg border border-border bg-surface shadow-sm">
          <EmptyState
            compact
            icon={CircleCheck}
            title="Nothing needs you right now"
            description="New high-fit jobs, CVs and drafts to review will show up here."
            action={
              <Button asChild size="sm" variant="default">
                <Link to="/discover?stage=open">
                  <Compass />
                  Browse Discover
                </Link>
              </Button>
            }
          />
        </div>
      )}

      <div className="grid grid-cols-3 gap-4 max-lg:grid-cols-1">
        <div className="col-span-2 space-y-4 max-lg:col-span-1">
          <Card
            icon={Compass}
            title="New high-fit jobs"
            count={data.new_high_fit_total}
            href={`/discover?min_score=${data.min_fit_score}`}
          >
            {data.new_high_fit.length === 0 ? (
              <Nothing text={`No new jobs above fit ${data.min_fit_score}`} />
            ) : (
              data.new_high_fit.map((j) => (
                <RowLink key={j.id} to={`/discover?job=${j.id}`}>
                  <FitBadge fit={j.fit} />
                  <TitleBlock title={j.title} subtitle={`${j.company.name} · ${j.location}`} />
                  <SourceBadge source={j.source} />
                  <span className="w-8 text-right text-xs text-fg-subtle tabular-nums">
                    {shortAge(j.posted_at)}
                  </span>
                </RowLink>
              ))
            )}
          </Card>

          <div className="grid grid-cols-2 gap-4">
            <Card icon={FileText} title="CVs to review" count={data.cvs_to_review.length}>
              {data.cvs_to_review.length === 0 ? (
                <Nothing text="No CVs waiting" />
              ) : (
                data.cvs_to_review.map((c) => (
                  <RowLink key={c.application_id} to={`/jobs/${c.job_id}/cv`}>
                    <TitleBlock title={c.job_title} subtitle={`${c.company_name} · v${c.version} draft`} />
                    <ArrowRight className="size-4 text-fg-subtle" />
                  </RowLink>
                ))
              )}
            </Card>
            <Card
              icon={Mail}
              title="Drafts to approve"
              count={data.drafts_to_approve.length}
              href="/outreach"
            >
              {data.drafts_to_approve.length === 0 ? (
                <Nothing text="No drafts waiting" />
              ) : (
                data.drafts_to_approve.map((d) => (
                  <RowLink key={d.draft_id} to={`/outreach?draft=${d.draft_id}`}>
                    <TitleBlock
                      title={d.contact_name ? `To ${d.contact_name}` : d.job_title}
                      subtitle={`${d.job_title} · ${d.company_name}`}
                    />
                    <ArrowRight className="size-4 text-fg-subtle" />
                  </RowLink>
                ))
              )}
            </Card>
          </div>

          <Card
            icon={Globe}
            title="Ready to apply manually"
            count={data.ready_to_apply.length}
            href="/pipeline?view=table"
          >
            {data.ready_to_apply.length === 0 ? (
              <Nothing text="No manual applications pending" />
            ) : (
              data.ready_to_apply.map((c) => (
                <div
                  key={c.application_id}
                  className="flex items-center gap-3 border-b border-border px-4 py-2.5 last:border-b-0"
                >
                  <FitBadge fit={c.fit} />
                  <Link to={`/jobs/${c.job_id}`} className="min-w-0 flex-1 hover:underline">
                    <TitleBlock title={c.title} subtitle={`${c.company_name} · CV approved`} />
                  </Link>
                  <Button size="sm" variant="ghost" asChild>
                    <Link to={`/jobs/${c.job_id}`}>
                      Listing & CV
                      <ArrowRight />
                    </Link>
                  </Button>
                  <Button size="sm" onClick={() => markApplied(c.application_id, c.title)}>
                    <CircleCheck />
                    Mark applied
                  </Button>
                </div>
              ))
            )}
          </Card>
        </div>

        <div className="space-y-4">
          <QueueCard queue={data.queue} />
          <Card icon={CalendarClock} title="Interviews" count={data.interviews.length} href="/pipeline">
            {data.interviews.length === 0 ? (
              <Nothing text="No interviews in progress" />
            ) : (
              data.interviews.map((c) => (
                <RowLink key={c.application_id} to={`/jobs/${c.job_id}`}>
                  <TitleBlock title={c.title} subtitle={c.company_name} />
                  <span className="text-xs text-fg-subtle">{relativeTime(c.stage_changed_at)}</span>
                </RowLink>
              ))
            )}
          </Card>
          <DiscoveryCard runs={data.last_runs} />
        </div>
      </div>
    </div>
  )
}
