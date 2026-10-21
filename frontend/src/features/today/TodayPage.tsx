import {
  ArrowRight,
  BellRing,
  CalendarClock,
  CircleCheck,
  Compass,
  FileText,
  Flame,
  Globe,
  Layers,
  type LucideIcon,
  Mail,
  Network,
  Package,
  Pause,
  Play,
  Radar,
  Send,
  TriangleAlert,
  UserRoundSearch,
  Users,
} from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { FitBadge, SourceBadge, ToneBadge } from '@/components/app/badges'
import { FoundCounter } from '@/components/app/contact/FoundCounter'
import { ProviderCredits } from '@/components/app/contact/ProviderCredits'
import { LinkedInSummaryList } from '@/components/app/linkedin/LinkedInSummaryList'
import { ChestSummary, StreakSummary } from '@/components/app/motivation/MotivationCards'
import { ScoringFallbackNotice } from '@/components/app/ScoringFallbackNotice'
import { ScoringProgress } from '@/components/app/ScoringProgress'
import { ScoringTodayCard } from '@/components/app/ScoringTodayCard'
import { EmptyState, ErrorState } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { TestDataBanner } from '@/components/app/TestDataBanner'
import { LogReplyDialog, MarkAppliedDialog, type TrackTarget } from '@/components/app/tracking/TrackingDialogs'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip } from '@/components/ui/tooltip'
import { useDiscoveryAction } from '@/hooks/useDiscoveryAction'
import { absoluteDate, clockTime, pluralize, relativeTime, shortAge, SOURCE_LABELS } from '@/lib/format'
import { useMotivation } from '@/lib/queries/motivation'
import { useReminderAction } from '@/lib/queries/tracking'
import { useQueueControl, useQueueDraft, useSources, useToday } from '@/lib/queries/workflow'
import { INTERVIEW_TYPE_LABELS, pct, shortDateTime } from '@/lib/tracking'
import type { Reminder, Today } from '@/lib/types'
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
  tour,
}: {
  icon: LucideIcon
  title: string
  count?: number
  href?: string
  hrefLabel?: string
  children: React.ReactNode
  className?: string
  tour?: string
}) {
  return (
    <section data-tour={tour} className={cn('flex flex-col rounded-lg border border-border bg-surface shadow-sm', className)}>
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
              ? `Next email in ${q.gap_min_minutes}-${q.gap_max_minutes} min, then a new random gap after each`
              : undefined,
        }),
      onError: (e) => toast.error(e.message),
    })
  return (
    <Card icon={Send} title="Send queue" href="/outreach?tab=queue" hrefLabel="Open" tour="today-queue">
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
            : `${queue.gap_min_minutes}-${queue.gap_max_minutes} min between sends${queue.status === 'running' && queue.estimated_finish_at ? ` · done about ${clockTime(queue.estimated_finish_at)}` : ''} · ${pluralize(queue.sent, 'email')} sent so far`}
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
    <Card icon={Radar} title="Last discovery" tour="today-discovery">
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
                      <span className="inline-flex items-center gap-1 text-xs text-danger-fg">
                        <TriangleAlert className="size-3.5" />
                        {r.status === 'failed' ? 'Failed' : 'Partial'}
                      </span>
                    </Tooltip>
                  ) : r.status === 'skipped' ? (
                    <Tooltip content={r.error}>
                      <span className="text-xs text-fg-subtle">Skipped</span>
                    </Tooltip>
                  ) : (
                    <span className="text-xs text-fg-subtle tabular-nums">{r.kept_count} kept</span>
                  )}
                  <span className="w-14 text-right text-xs text-fg-muted tabular-nums">
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

/** Source problems belong on Today, not only in logs. */
function SourceAlerts() {
  const { data } = useSources()
  const problems = (data ?? []).filter(
    (s) => s.enabled && (!s.configured || s.last_run?.status === 'failed'),
  )
  if (!problems.length) return null
  return (
    <div role="alert" className="flex items-start gap-3 rounded-lg border border-tone-red-border bg-danger-bg px-4 py-3">
      <TriangleAlert className="mt-0.5 size-4 shrink-0 text-danger-fg" />
      <div className="min-w-0 flex-1 space-y-0.5 text-sm">
        <p className="font-medium text-danger-fg">
          {problems.length === 1 ? `${problems[0].name} needs attention` : `${problems.length} sources need attention`}
        </p>
        {problems.map((s) => (
          <p key={s.source} className="truncate text-xs text-fg-muted">
            <span className="font-medium text-fg">{s.name}:</span>{' '}
            {!s.configured ? `not configured (${s.config_hint})` : s.last_run?.error}
          </p>
        ))}
      </div>
      <Button size="sm" asChild>
        <Link to="/settings?section=sources">Open sources</Link>
      </Button>
    </div>
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
      <div className="mt-5 flex flex-wrap gap-2">
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
        <TourButton tour="today" label="Tour the app with sample data" />
      </div>
    </div>
  )
}

/** The email route, step by step: drafts to review, approved emails to queue, the queue. */
function EmailsCard({ data }: { data: Today }) {
  const queueDraft = useQueueDraft()
  const q = data.queue
  const total = data.drafts_to_approve.length + data.emails_to_queue.length
  return (
    <Card icon={Mail} title="Cold emails" tour="today-emails" count={total} href="/outreach">
      {total === 0 ? (
        <Nothing text="No emails waiting on you" />
      ) : (
        <>
          {data.drafts_to_approve.map((d) => (
            <RowLink key={`r-${d.draft_id}`} to={`/jobs/${d.job_id}#outreach`}>
              <TitleBlock title={d.contact_name ? `Review: to ${d.contact_name}` : `Review: ${d.job_title}`} subtitle={`${d.job_title} · ${d.company_name}`} />
              <ArrowRight className="size-4 text-fg-subtle" />
            </RowLink>
          ))}
          {data.emails_to_queue.map((d) => (
            <div key={`q-${d.draft_id}`} className="flex items-center gap-3 border-b border-border px-4 py-2.5 last:border-b-0">
              <Link to={`/jobs/${d.job_id}#outreach`} className="min-w-0 flex-1 hover:underline">
                <TitleBlock title={`Ready to send: to ${d.contact_name ?? d.company_name}`} subtitle={`${d.job_title} · ${d.company_name}`} />
              </Link>
              <Button
                size="sm"
                onClick={() =>
                  queueDraft.mutate(d.draft_id, { onSuccess: () => toast.success('Added to the send queue'), onError: (e) => toast.error(e.message) })
                }
                disabled={queueDraft.isPending}
              >
                Add to queue
              </Button>
            </div>
          ))}
        </>
      )}
      <Link to="/outreach?tab=queue" className="flex items-center gap-2 border-t border-border px-4 py-2 text-xs text-fg-muted hover:text-fg">
        Queue {q.status === 'running' ? 'running' : q.status}: {q.pending} waiting
        {q.status === 'running' && q.next_send_at ? ` · next ${clockTime(q.next_send_at)}` : ''}
        <ArrowRight className="ml-auto size-3.5" />
      </Link>
    </Card>
  )
}

function FollowUpsCard({ reminders }: { reminders: Reminder[] }) {
  const act = useReminderAction()
  const [replying, setReplying] = useState<TrackTarget | null>(null)
  const run = (r: Reminder, action: 'snooze' | 'dismiss' | 'confirm', done: string) =>
    act.mutate(
      { appId: r.application_id, key: r.key, action },
      { onSuccess: () => toast.success(done, { description: r.job_title }), onError: (e) => toast.error(e.message) },
    )
  return (
    <Card icon={BellRing} title="Follow-ups" tour="today-followups" count={reminders.length} href="/applications?tab=applied">
      {reminders.length === 0 ? (
        <Nothing text="No follow-ups due" />
      ) : (
        reminders.map((r) => (
          <div key={`${r.application_id}-${r.key}`} className="flex items-center gap-3 border-b border-border px-4 py-2.5 last:border-b-0">
            <Link to={`/jobs/${r.job_id}`} className="min-w-0 flex-1 hover:underline">
              <TitleBlock
                title={r.job_title}
                subtitle={
                  r.kind === 'ghost'
                    ? `${r.company} · no reply in ${r.days} days: close as no response?`
                    : `${r.company} · applied ${r.days}+ days ago, no reply: follow up`
                }
              />
            </Link>
            {r.kind === 'ghost' ? (
              <>
                <Button size="sm" variant="ghost" onClick={() => run(r, 'dismiss', 'Kept open')}>
                  Not yet
                </Button>
                <Button size="sm" onClick={() => run(r, 'confirm', 'Closed as no response')}>
                  Close as no response
                </Button>
              </>
            ) : (
              <>
                <Button size="sm" variant="ghost" onClick={() => run(r, 'snooze', 'Snoozed for 3 days')}>
                  Snooze
                </Button>
                <Button size="sm" variant="ghost" onClick={() => run(r, 'dismiss', 'Follow-up dismissed')}>
                  Dismiss
                </Button>
                <Button size="sm" onClick={() => setReplying({ appId: r.application_id, title: r.job_title, company: r.company })}>
                  Log reply
                </Button>
              </>
            )}
          </div>
        ))
      )}
      <LogReplyDialog
        key={replying?.appId ?? 'none'}
        target={replying}
        onOpenChange={(o) => !o && setReplying(null)}
        onLogged={() => toast.success('Reply logged', { description: replying?.title })}
      />
    </Card>
  )
}

/** Streak and chest (Settings → Motivation): nothing here blocks the work above. */
function MotivationColumn() {
  const { data } = useMotivation()
  if (!data?.enabled) return null
  return (
    <>
      <Card icon={Flame} title="Streak" tour="today-streak" href="/motivation?tab=wins" hrefLabel="Wins">
        <StreakSummary data={data} />
      </Card>
      <Card icon={Package} title="Chest" tour="today-chest" count={data.chests.available || undefined} href="/motivation?tab=shop" hrefLabel="Shop">
        <ChestSummary data={data} />
      </Card>
    </>
  )
}

export default function TodayPage() {
  const { data, isPending, error, refetch } = useToday()
  const [applying, setApplying] = useState<TrackTarget | null>(null)

  if (isPending) return <TodaySkeleton />
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />

  const attention =
    data.new_high_fit_total +
    data.cvs_to_review.length +
    data.drafts_to_approve.length +
    data.emails_to_queue.length +
    data.ready_to_apply.length +
    data.reminders.length +
    (data.contacts_to_get?.total ?? 0)
  const summary = data.stats_summary
  const date = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-6 py-6">
      <header data-tour="today-greeting">
        <h1 className="text-xl font-semibold tracking-tight">{greeting()}</h1>
        <p className="text-sm text-fg-muted">
          {date} ·{' '}
          {data.last_runs.length === 0
            ? "Let's get you set up."
            : attention === 0
              ? "You're all caught up."
              : `${pluralize(attention, 'thing needs', 'things need')} your attention.`}
          {summary.applied_total > 0 && (
            <Link to="/applications?tab=stats" data-tour="today-stats" className="hover:text-fg">
              {' '}
              · {summary.applied_this_week} applied this week · response rate {pct(summary.response_rate)} ({summary.responded}/
              {summary.applied_total})
            </Link>
          )}
        </p>
      </header>
      <ScoringFallbackNotice className="rounded-lg border px-4" />
      <ScoringProgress className="rounded-lg border px-4" />
      <ScoringTodayCard />

      <SourceAlerts />
      <TestDataBanner showLink />

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
            tour="today-high-fit"
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

          <div className="grid grid-cols-2 gap-4" data-tour="today-review">
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
            <EmailsCard data={data} />
          </div>

          {data.contacts_to_get && data.contacts_to_get.total > 0 && (
            <Card
              icon={UserRoundSearch}
              title="Contacts to get"
              tour="today-contacts-to-get"
              count={data.contacts_to_get.total}
              href="/outreach?tab=contacts"
              hrefLabel="Work through them"
            >
              <div className="px-4 pt-1 pb-2">
                <FoundCounter found={data.contacts_to_get.found_today} limit={data.contacts_to_get.daily_limit} />
                <ProviderCredits className="mt-1" />
              </div>
              {data.contacts_to_get.items.map((i) => (
                <RowLink key={`cg-${i.application_id}`} to={`/outreach?tab=contacts&app=${i.application_id}`}>
                  <TitleBlock
                    title={i.company_name}
                    subtitle={`${i.job_title} · ${i.state === 'verify' ? `verify ${i.contact_name ?? 'the contact'}` : i.nobody_found ? 'nobody found yet' : 'find who to write to'}`}
                  />
                  <FitBadge fit={i.fit} size="sm" />
                </RowLink>
              ))}
            </Card>
          )}
          {data.linkedin && (
            <Card icon={Network} title="LinkedIn" tour="today-linkedin" href="/linkedin" hrefLabel="Open LinkedIn" count={data.linkedin.to_send.length + data.linkedin.followups.length + data.linkedin.to_decide_total}>
              <div className="px-2 py-2">
                <LinkedInSummaryList data={data.linkedin} />
              </div>
            </Card>
          )}
          {data.also_email.length > 0 && (
            <Card icon={Mail} title="Also email someone there" tour="today-also-email" count={data.also_email.length} href="/pipeline">
              {data.also_email.map((c) => (
                <RowLink key={`ae-${c.application_id}`} to={`/jobs/${c.job_id}#outreach`}>
                  <TitleBlock
                    title={c.title}
                    subtitle={`${c.company_name} · applied on the website · ${c.tracks.outreach === 'contact' ? `write to ${c.tracks.contact_name}` : c.tracks.outreach === 'verify' ? `verify ${c.tracks.contact_name}` : 'find who to write to'}`}
                  />
                  <ArrowRight className="size-4 text-fg-subtle" />
                </RowLink>
              ))}
            </Card>
          )}
          <Card
            icon={Globe}
            title="Ready to apply on the website"
            tour="today-manual"
            count={data.ready_to_apply.length}
            href="/applications?tab=ready"
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
                    <TitleBlock title={c.title} subtitle={`${c.company_name} · CV approved${c.tracks.outreach === 'sent' ? ' · already emailed' : ''}`} />
                  </Link>
                  <Button size="sm" variant="ghost" asChild>
                    <Link to="/applications?tab=ready">
                      Listing & CV
                      <ArrowRight />
                    </Link>
                  </Button>
                  <Button size="sm" onClick={() => setApplying({ appId: c.application_id, title: c.title, company: c.company_name })}>
                    <CircleCheck />
                    Mark applied
                  </Button>
                </div>
              ))
            )}
          </Card>
          <FollowUpsCard reminders={data.reminders} />
        </div>

        <div className="space-y-4">
          <MotivationColumn />
          <QueueCard queue={data.queue} />
          <Card
            icon={CalendarClock}
            title="Upcoming interviews"
            tour="today-interviews"
            count={data.upcoming_interviews.length}
            href="/applications?tab=applied&stage=interview"
          >
            {data.upcoming_interviews.length === 0 ? (
              <Nothing text="No interviews in the next 14 days" />
            ) : (
              data.upcoming_interviews.map((i) => (
                <RowLink key={i.interview_id} to={`/jobs/${i.job_id}`}>
                  <TitleBlock
                    title={i.job_title}
                    subtitle={`${i.company_name} · round ${i.round}, ${INTERVIEW_TYPE_LABELS[i.type].toLowerCase()}`}
                  />
                  <span className="text-xs whitespace-nowrap text-fg-subtle">{shortDateTime(i.scheduled_at)}</span>
                </RowLink>
              ))
            )}
          </Card>
          <DiscoveryCard runs={data.last_runs} />
        </div>
      </div>
      <MarkAppliedDialog
        key={applying?.appId ?? 'none'}
        target={applying}
        cvVersion={null}
        onOpenChange={(o) => !o && setApplying(null)}
      />
    </div>
  )
}
