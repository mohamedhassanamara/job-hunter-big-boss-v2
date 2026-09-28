import { CircleCheck, Clock, Inbox, Pause, Play, RotateCcw, ShieldCheck, Trash2 } from 'lucide-react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { ToneBadge, type Tone } from '@/components/app/badges'
import { EmptyState, ErrorState, SkeletonRows } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { Tooltip } from '@/components/ui/tooltip'
import { useNow } from '@/hooks/useNow'
import { absoluteDate, clockTime, relativeTime } from '@/lib/format'
import { useQueue, useQueueControl, useQueueItemAction, useRemoveQueueItem } from '@/lib/queries/workflow'
import type { QueueItem } from '@/lib/types'

const ITEM_STATUS: Record<QueueItem['status'], { tone: Tone; label: string }> = {
  pending: { tone: 'amber', label: 'Pending' },
  sending: { tone: 'blue', label: 'Sending' },
  sent: { tone: 'green', label: 'Sent' },
  failed: { tone: 'red', label: 'Failed' },
  cancelled: { tone: 'gray', label: 'Cancelled' },
  unknown: { tone: 'amber', label: 'Check Gmail' },
}

function countdown(target: string | null, now: number) {
  if (!target) return null
  const ms = Math.max(0, new Date(target).getTime() - now)
  const m = Math.floor(ms / 60000)
  const s = Math.floor((ms % 60000) / 1000)
  return `${m}:${String(s).padStart(2, '0')}`
}

export function QueueTab() {
  const { data: queue, isPending, error, refetch } = useQueue()
  const control = useQueueControl()
  const remove = useRemoveQueueItem()
  const itemAction = useQueueItemAction()
  const running = queue?.status === 'running'
  const now = useNow(1000, running)

  if (isPending) return <SkeletonRows rows={6} className="mx-6 my-5" />
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />

  const toggle = () =>
    control.mutate(running ? 'pause' : 'resume', {
      onSuccess: (q) => toast.success(q.status === 'running' ? 'Queue resumed' : 'Queue paused'),
      onError: (e) => toast.error(e.message),
    })

  return (
    <div data-tour="outreach-queue" className="mx-auto max-w-5xl space-y-4 px-6 py-5">
      <div className="flex items-center gap-6 rounded-lg border border-border bg-surface p-4 shadow-sm">
        <div className="space-y-1">
          <ToneBadge tone={running ? 'green' : queue.status === 'paused' ? 'amber' : 'gray'}>
            {running ? 'Running' : queue.status === 'paused' ? 'Paused' : 'Idle'}
          </ToneBadge>
          <p className="text-xs text-fg-subtle">
            {queue.interval_minutes} min between sends · max {queue.max_items} per queue
          </p>
        </div>
        <div className="h-10 w-px bg-border" />
        <dl className="flex gap-8">
          <div>
            <dt className="text-xs text-fg-subtle">Pending</dt>
            <dd className="text-xl font-semibold tabular-nums">{queue.counts.pending}</dd>
          </div>
          <div>
            <dt className="text-xs text-fg-subtle">Sent</dt>
            <dd className="text-xl font-semibold tabular-nums">{queue.counts.sent}</dd>
          </div>
          <div>
            <dt className="text-xs text-fg-subtle">Next send in</dt>
            <dd className="text-xl font-semibold tabular-nums">
              {running && queue.counts.pending > 0 ? countdown(queue.next_send_at, now) : '—'}
            </dd>
          </div>
        </dl>
        <div className="ml-auto">
          {queue.counts.pending > 0 && (
            <Tooltip content={!running && !queue.test_sent ? 'Send one test email to yourself first (open a draft → Send test to me)' : null}>
              <span>
                <Button variant="default" onClick={toggle} disabled={control.isPending || (!running && !queue.test_sent)}>
                  {running ? <Pause /> : <Play />}
                  {running ? 'Pause queue' : 'Start sending'}
                </Button>
              </span>
            </Tooltip>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2 rounded-md border border-border bg-bg-subtle px-3 py-2 text-xs text-fg-muted">
        <ShieldCheck className="size-3.5 text-fg-subtle" />
        {queue.test_sent
          ? `Real emails go out through your Gmail, with the approved CV attached. Every attempt is logged; a failure stops only that email (a login problem pauses the queue).`
          : `Nothing is sent until one test email reaches ${queue.own_address || 'your own address'}: open a draft and use “Send test to me”.`}
      </div>

      {queue.items.length === 0 ? (
        <div className="rounded-lg border border-border bg-surface shadow-sm">
          <EmptyState
            icon={Inbox}
            title="Queue is empty"
            description="Approved drafts land here and go out one at a time."
            action={
              <Button size="sm" asChild>
                <Link to="/outreach">Review drafts</Link>
              </Button>
            }
          />
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-sm">
          <table className="w-full table-fixed text-sm">
            <thead className="bg-bg-subtle">
              <tr className="border-b border-border text-left text-xs text-fg-muted">
                <th className="h-9 w-12 px-3 font-medium">#</th>
                <th className="w-52 px-3 font-medium">Recipient</th>
                <th className="px-3 font-medium">Subject</th>
                <th className="w-36 px-3 font-medium">When</th>
                <th className="w-28 px-3 font-medium">Status</th>
                <th className="w-20 px-3" />
              </tr>
            </thead>
            <tbody>
              {queue.items.map((item, i) => {
                const pending = item.status === 'pending'
                const when = item.sent_at ?? item.scheduled_at
                return (
                  <tr key={item.id} className="h-12 border-b border-border last:border-b-0">
                    <td className="px-3 text-xs text-fg-subtle tabular-nums">{pending ? i + 1 : ''}</td>
                    <td className="px-3">
                      <p className="truncate font-medium">{item.contact_name}</p>
                      <p className="truncate text-xs text-fg-muted">{item.company_name}</p>
                    </td>
                    <td className="truncate px-3">
                      <Link to={`/jobs/${item.job_id}`} className="hover:underline">
                        {item.subject}
                      </Link>
                    </td>
                    <td className="px-3 text-xs text-fg-muted tabular-nums">
                      {pending ? (
                        when ? (
                          <span className="inline-flex items-center gap-1">
                            <Clock className="size-3.5 text-fg-subtle" />
                            {clockTime(when)}
                          </span>
                        ) : (
                          <span className="text-fg-subtle">When resumed</span>
                        )
                      ) : (
                        <Tooltip content={absoluteDate(when)}>
                          <span>{relativeTime(when)}</span>
                        </Tooltip>
                      )}
                    </td>
                    <td className="px-3">
                      <Tooltip content={item.error}>
                        <span>
                          <ToneBadge tone={ITEM_STATUS[item.status].tone}>{ITEM_STATUS[item.status].label}</ToneBadge>
                        </span>
                      </Tooltip>
                    </td>
                    <td className="px-2">
                      {(item.status === 'failed' || item.status === 'unknown') && (
                        <div className="flex items-center gap-0.5">
                          <Tooltip content={item.error ?? 'Retry'}>
                            <Button
                              size="icon-sm"
                              variant="ghost"
                              aria-label="Retry"
                              onClick={() =>
                                itemAction.mutate(
                                  { itemId: item.id, action: 'retry' },
                                  { onSuccess: () => toast.success('Back in the queue'), onError: (e) => toast.error(e.message) },
                                )
                              }
                            >
                              <RotateCcw />
                            </Button>
                          </Tooltip>
                          {item.status === 'unknown' && (
                            <Tooltip content="I found it in Gmail's Sent folder">
                              <Button
                                size="icon-sm"
                                variant="ghost"
                                aria-label="Mark as sent"
                                onClick={() =>
                                  itemAction.mutate(
                                    { itemId: item.id, action: 'mark-sent' },
                                    { onSuccess: () => toast.success('Marked as sent'), onError: (e) => toast.error(e.message) },
                                  )
                                }
                              >
                                <CircleCheck />
                              </Button>
                            </Tooltip>
                          )}
                        </div>
                      )}
                      {pending && (
                        <Tooltip content="Remove from queue (back to review)">
                          <Button
                            size="icon-sm"
                            variant="ghost"
                            aria-label="Remove from queue"
                            onClick={() =>
                              remove.mutate(item.id, {
                                onSuccess: () =>
                                  toast.success('Removed from queue', {
                                    description: 'The draft is back in review.',
                                  }),
                                onError: (e) => toast.error(e.message),
                              })
                            }
                          >
                            <Trash2 />
                          </Button>
                        </Tooltip>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
