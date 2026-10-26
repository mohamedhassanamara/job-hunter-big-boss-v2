import { ArrowRight, FileCheck, Globe, Layers, Mail, Send } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Link } from 'react-router'
import { FindBatchButton } from '@/components/app/contact/FindBatch'
import { clockTime } from '@/lib/format'
import { useNavCounts } from '@/lib/queries/workflow'
import type { Today } from '@/lib/types'
import { cn } from '@/lib/utils'

function Pass({ n, icon: Icon, label, count, to, hint }: { n: number; icon: LucideIcon; label: string; count: number; to: string; hint: string }) {
  return (
    <Link
      to={to}
      className={cn(
        'group flex flex-1 items-center gap-3 rounded-md border border-border px-3 py-2.5 transition-colors duration-120 hover:bg-surface-hover',
        count === 0 && 'opacity-70',
      )}
    >
      <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-primary-subtle text-2xs font-semibold text-primary">{n}</span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5 text-sm font-medium">
          <Icon className="size-3.5 text-fg-subtle" strokeWidth={1.75} />
          {label}
          <span className="rounded-sm bg-surface-selected px-1.5 text-2xs font-semibold tabular-nums">{count}</span>
        </span>
        <span className="block truncate text-2xs text-fg-subtle">{hint}</span>
      </span>
      <ArrowRight className="size-3.5 text-fg-subtle transition-transform duration-120 group-hover:translate-x-0.5" />
    </Link>
  )
}

/** The batch as three passes: CVs to review, emails to review, jobs to apply, each opening its list,
 * with the send queue under them. */
export function BatchCard({ queue }: { queue: Today['queue'] }) {
  const counts = useNavCounts().data
  if (!counts) return null
  const open = counts.cvs_to_review + counts.outreach_review + counts.ready_to_apply + queue.pending
  if (open === 0) return null
  const running = queue.status === 'running'
  return (
    <section data-tour="today-batch" className="rounded-lg border border-border bg-surface shadow-sm">
      <div className="flex h-11 items-center gap-2 border-b border-border px-4">
        <Layers className="size-4 text-fg-subtle" strokeWidth={1.75} />
        <h2 className="text-sm font-semibold">This batch</h2>
        <span className="text-xs text-fg-subtle">three passes, each a list with J/K and one key</span>
        <FindBatchButton className="ml-auto" />
      </div>
      <div className="flex gap-3 p-3 max-lg:flex-col">
        <Pass n={1} icon={FileCheck} label="CVs to review" count={counts.cvs_to_review} to="/review-cvs" hint="A approves, R regenerates, E edits the summary" />
        <Pass n={2} icon={Mail} label="Emails to review" count={counts.outreach_review} to="/outreach" hint="A approves and queues the email" />
        <Pass n={3} icon={Globe} label="Jobs to apply" count={counts.ready_to_apply} to="/applications?tab=ready" hint="A marks applied, Enter confirms, next opens" />
      </div>
      <Link to="/outreach?tab=queue" className="flex items-center gap-2 border-t border-border px-4 py-2 text-xs text-fg-muted hover:text-fg">
        <Send className="size-3.5" />
        Send queue {running ? 'running' : queue.status}: {queue.pending} waiting
        {running && queue.next_send_at ? ` · next ${clockTime(queue.next_send_at)}` : ''}
        <ArrowRight className="ml-auto size-3.5" />
      </Link>
    </section>
  )
}
