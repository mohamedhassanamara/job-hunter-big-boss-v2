import { CalendarClock, Download, MessageSquareReply, XCircle } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { ToneBadge, type Tone } from '@/components/app/badges'
import { CloseDialog } from '@/components/app/CloseDialog'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { apiUrl } from '@/lib/api'
import { pluralize } from '@/lib/format'
import { useCloseApplication, useUpdateInterview } from '@/lib/queries/tracking'
import {
  CLOSE_REASON_LABELS,
  INTERVIEW_TYPE_LABELS,
  isApplied,
  METHOD_LABELS,
  OUTCOME_LABELS,
  RESPONSE_LABELS,
  shortDate,
  shortDateTime,
} from '@/lib/tracking'
import type { InterviewOutcome, ResponseKind, Stage, TrackedApplication } from '@/lib/types'
import { LogInterviewDialog, LogReplyDialog, type TrackTarget } from './TrackingDialogs'

const REPLY_TONE: Record<ResponseKind, Tone> = { positive: 'green', rejection: 'red', other: 'gray', do_not_contact: 'red' }
const OUTCOME_TONE: Record<InterviewOutcome, Tone> = { pending: 'amber', passed: 'green', failed: 'red', cancelled: 'gray' }

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-fg-subtle">{label}</dt>
      <dd className="truncate text-sm">{children}</dd>
    </div>
  )
}

/** How and when you applied, the (locked) CV sent, replies and interview rounds. */
export function AppliedFacts({ tracking }: { tracking: TrackedApplication }) {
  const update = useUpdateInterview()
  const t = tracking
  return (
    <div className="space-y-4 p-4">
      <dl className="grid grid-cols-3 gap-3">
        <Fact label="Applied on">{shortDate(t.applied_at)}</Fact>
        <Fact label="Method">{t.applied_method ? METHOD_LABELS[t.applied_method] : '—'}</Fact>
        <Fact label="CV sent">
          {t.applied_cv_version_id ? (
            <a
              className="inline-flex items-center gap-1 hover:underline"
              href={apiUrl(`/cv/${t.applied_cv_version_id}/pdf`, { download: true })}
            >
              v{t.applied_cv_version} (locked)
              <Download className="size-3.5 text-fg-subtle" />
            </a>
          ) : (
            '—'
          )}
        </Fact>
        {t.applied_cover_letter_id && (
          <Fact label="Cover letter sent">
            <a
              className="inline-flex items-center gap-1 hover:underline"
              href={apiUrl(`/letters/${t.applied_cover_letter_id}/pdf`, { download: true })}
            >
              v{t.applied_cover_letter_version} (locked)
              <Download className="size-3.5 text-fg-subtle" />
            </a>
          </Fact>
        )}
      </dl>
      {t.applied_notes && <p className="text-sm whitespace-pre-line text-fg-muted">{t.applied_notes}</p>}
      {t.close_reason && t.stage === 'closed' && (
        <p className="text-sm">
          Closed: <span className="font-medium">{CLOSE_REASON_LABELS[t.close_reason]}</span>
        </p>
      )}
      <div className="space-y-2">
        <p className="text-xs font-medium text-fg-subtle">
          Replies{t.days_to_first_response !== null && ` · first answer after ${pluralize(Math.round(t.days_to_first_response), 'day')}`}
        </p>
        {t.responses.length === 0 ? (
          <p className="text-sm text-fg-muted">No reply logged yet.</p>
        ) : (
          <ul className="space-y-1.5">
            {t.responses.map((r) => (
              <li key={r.id} className="flex items-start gap-2 text-sm">
                <ToneBadge tone={REPLY_TONE[r.kind]}>{RESPONSE_LABELS[r.kind]}</ToneBadge>
                <span className="text-xs leading-5 text-fg-subtle">{shortDate(r.received_at)}</span>
                {r.notes && <span className="min-w-0 flex-1 text-fg-muted">{r.notes}</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="space-y-2">
        <p className="text-xs font-medium text-fg-subtle">Interviews</p>
        {t.interviews.length === 0 ? (
          <p className="text-sm text-fg-muted">No interview logged yet.</p>
        ) : (
          <ul className="space-y-2">
            {t.interviews.map((i) => (
              <li key={i.id} className="flex items-center gap-2 text-sm">
                <span className="w-16 shrink-0 font-medium">Round {i.round}</span>
                <span className="min-w-0 flex-1 truncate">
                  {INTERVIEW_TYPE_LABELS[i.type]} · <span className="text-fg-muted">{shortDateTime(i.scheduled_at)}</span>
                </span>
                {t.stage === 'closed' ? (
                  <ToneBadge tone={OUTCOME_TONE[i.outcome]}>{OUTCOME_LABELS[i.outcome]}</ToneBadge>
                ) : (
                  <Select
                    size="sm"
                    aria-label={`Round ${i.round} outcome`}
                    value={i.outcome}
                    onValueChange={(v) =>
                      update.mutate(
                        { id: i.id, outcome: v as InterviewOutcome },
                        { onError: (e) => toast.error(e.message) },
                      )
                    }
                    options={(Object.keys(OUTCOME_LABELS) as InterviewOutcome[]).map((o) => ({ value: o, label: OUTCOME_LABELS[o] }))}
                    className="w-28"
                  />
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

/** Log reply / Log interview / Close… for an applied job. A reply suggests the obvious next step
 * (interview after a positive reply, close after a rejection); nothing moves on its own. */
export function TrackingActions({
  target,
  stage,
  rounds,
  primary = 'reply',
}: {
  target: TrackTarget
  stage: Stage
  rounds: number
  primary?: 'reply' | 'none'
}) {
  const [dialog, setDialog] = useState<'reply' | 'interview' | 'close' | null>(null)
  const close = useCloseApplication()
  if (!isApplied(stage)) return null

  const doClose = (reason: Parameters<typeof close.mutate>[0]['reason']) =>
    close.mutate(
      { appId: target.appId, reason },
      {
        onSuccess: () => toast.success(`Closed: ${CLOSE_REASON_LABELS[reason].toLowerCase()}`, { description: target.title }),
        onError: (e) => toast.error(e.message),
      },
    )

  const onLogged = (kind: ResponseKind) => {
    if (kind === 'positive') {
      toast.success('Positive reply logged', {
        description: 'Next: log the interview when it is scheduled.',
        duration: 10000,
        action: { label: 'Log interview', onClick: () => setDialog('interview') },
      })
    } else if (kind === 'rejection') {
      toast.success('Rejection logged', {
        description: 'Close the application as rejected?',
        duration: 10000,
        action: { label: 'Close as rejected', onClick: () => doClose('rejected') },
      })
    } else {
      toast.success('Reply logged', { description: target.title })
    }
  }

  return (
    <>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant={primary === 'reply' ? 'default' : 'secondary'} onClick={() => setDialog('reply')}>
          <MessageSquareReply />
          Log reply
        </Button>
        <Button size="sm" onClick={() => setDialog('interview')}>
          <CalendarClock />
          Log interview
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setDialog('close')}
        >
          <XCircle />
          Close…
        </Button>
      </div>
      <LogReplyDialog
        key={`reply-${dialog === 'reply'}`}
        target={dialog === 'reply' ? target : null}
        onOpenChange={(o) => !o && setDialog(null)}
        onLogged={onLogged}
      />
      <LogInterviewDialog
        key={`interview-${dialog === 'interview'}-${rounds}`}
        target={dialog === 'interview' ? target : null}
        round={rounds + 1}
        onOpenChange={(o) => !o && setDialog(null)}
      />
      <CloseDialog
        key={`close-${dialog === 'close'}`}
        open={dialog === 'close'}
        applied
        title={`${target.title} · ${target.company}`}
        onCancel={() => setDialog(null)}
        onConfirm={(reason) => {
          setDialog(null)
          doClose(reason)
        }}
      />
    </>
  )
}
