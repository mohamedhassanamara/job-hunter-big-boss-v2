import {
  ArrowRightLeft,
  BellRing,
  CalendarClock,
  MessageSquareReply,
  CircleCheck,
  FileCheck,
  FileText,
  type LucideIcon,
  Mail,
  MailCheck,
  Radar,
  Send,
  StickyNote,
  UserRoundCheck,
} from 'lucide-react'
import { StageDot } from '@/components/app/badges'
import { Tooltip } from '@/components/ui/tooltip'
import { absoluteDate, relativeTime } from '@/lib/format'
import type { TimelineEvent } from '@/lib/types'

const ICONS: Record<string, LucideIcon> = {
  discovered: Radar,
  stage_change: ArrowRightLeft,
  note: StickyNote,
  cv_generated: FileText,
  cv_approved: FileCheck,
  draft_created: Mail,
  draft_approved: MailCheck,
  sent: Send,
  applied: CircleCheck,
  contact_resolved: UserRoundCheck,
  response: MessageSquareReply,
  interview: CalendarClock,
  reminder: BellRing,
}

export function Timeline({ events }: { events: TimelineEvent[] }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <p className="mb-3 text-xs font-medium text-fg-subtle">Timeline</p>
      {events.length === 0 ? (
        <p className="text-sm text-fg-muted">No activity yet.</p>
      ) : (
        <ol className="relative space-y-3">
          <span className="absolute top-2 bottom-2 left-[9px] w-px bg-border" aria-hidden />
          {events.map((e) => {
            const Icon = ICONS[e.kind] ?? StickyNote
            return (
              <li key={e.id} className="relative flex gap-3">
                <span className="z-10 flex size-5 shrink-0 items-center justify-center rounded-full border border-border bg-surface">
                  {e.kind === 'stage_change' && e.to_stage ? (
                    <StageDot stage={e.to_stage} className="size-2" />
                  ) : (
                    <Icon className="size-3 text-fg-subtle" />
                  )}
                </span>
                <div className="min-w-0 flex-1 pt-px">
                  <p className="text-sm leading-snug">{e.message}</p>
                  <Tooltip content={absoluteDate(e.at)}>
                    <span className="text-xs text-fg-subtle">{relativeTime(e.at)}</span>
                  </Tooltip>
                </div>
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}
