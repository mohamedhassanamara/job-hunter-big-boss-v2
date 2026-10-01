import { ArrowRight, Check, Clock, ExternalLink, Send } from 'lucide-react'
import { Link } from 'react-router'
import type { LinkedInSummary } from '@/lib/types'
import { relativeTime } from '@/lib/format'
import { cn } from '@/lib/utils'

const FOLLOWUP = {
  no_answer: 'no answer to the request',
  no_reply: 'no reply to your follow-up',
  write_followup: 'accepted: write the follow-up',
} as const

function Row({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <Link to={to} className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-surface-hover">
      {children}
      <ArrowRight className="ml-auto size-3.5 shrink-0 text-fg-subtle" />
    </Link>
  )
}

/** The LinkedIn to-dos (Today card and the LinkedIn page share it). */
export function LinkedInSummaryList({ data }: { data: LinkedInSummary }) {
  const nothing = data.links_unopened === 0 && data.to_decide.length === 0 && data.to_send.length === 0 && data.followups.length === 0
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-2 text-xs text-fg-muted">
        <Link to="/linkedin" className={cn('hover:underline', data.links_unopened > 0 && 'text-fg')}>
          {data.links_unopened > 0 ? `${data.links_unopened} of ${data.links_total} searches not opened today` : `All ${data.links_total} searches opened today`}
        </Link>
        <span className={cn('tabular-nums', data.requests_today >= data.daily_limit && 'text-warning-fg')}>
          {data.requests_today} / {data.daily_limit} requests today
        </span>
      </div>
      {nothing && (
        <p className="flex items-center gap-2 px-2 text-sm text-fg-muted">
          <Check className="size-4 text-success-fg" />
          Nothing waiting on LinkedIn.
        </p>
      )}
      {data.to_decide.length > 0 && (
        <div>
          <p className="px-2 text-2xs font-medium text-fg-subtle">Imported, to decide on ({data.to_decide_total})</p>
          {data.to_decide.map((j) => (
            <Row key={`d-${j.job_id}`} to={`/jobs/${j.job_id}`}>
              <ExternalLink className="size-3.5 shrink-0 text-fg-subtle" />
              <span className="truncate">{j.title}</span>
              <span className="truncate text-xs text-fg-subtle">{j.company}</span>
            </Row>
          ))}
        </div>
      )}
      {data.to_send.length > 0 && (
        <div>
          <p className="px-2 text-2xs font-medium text-fg-subtle">Requests to send</p>
          {data.to_send.map((r) => (
            <Row key={`s-${r.row_id}`} to={`/jobs/${r.job_id}#linkedin`}>
              <Send className="size-3.5 shrink-0 text-fg-subtle" />
              <span className="truncate">{r.person}</span>
              <span className="truncate text-xs text-fg-subtle">
                {r.company} · {r.note_ready ? 'note ready' : 'draft the note'}
              </span>
            </Row>
          ))}
        </div>
      )}
      {data.followups.length > 0 && (
        <div>
          <p className="px-2 text-2xs font-medium text-fg-subtle">Follow-ups</p>
          {data.followups.map((f) => (
            <Row key={`f-${f.row_id}`} to={`/jobs/${f.job_id}#linkedin`}>
              <Clock className="size-3.5 shrink-0 text-fg-subtle" />
              <span className="truncate">{f.person}</span>
              <span className="truncate text-xs text-fg-subtle">
                {f.company} · {FOLLOWUP[f.kind]} · {relativeTime(f.since)}
              </span>
            </Row>
          ))}
        </div>
      )}
    </div>
  )
}
