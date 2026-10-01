import { CircleCheck, CircleX, FileText, ListPlus, Mail, RefreshCw, RotateCcw, Send, TriangleAlert, X } from 'lucide-react'
import { CritiqueButton } from '@/components/app/CritiqueButton'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { FitBadge, ToneBadge } from '@/components/app/badges'
import { ContactAlertBanner } from '@/components/app/ContactAlertBanner'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input, Textarea } from '@/components/ui/input'
import { Kbd } from '@/components/ui/kbd'
import { Label } from '@/components/ui/label'
import { Tooltip } from '@/components/ui/tooltip'
import { relativeTime } from '@/lib/format'
import { useDraftAction, useDraftRun, useMentionApplication, useQueueDraft, useSaveDraft, useTestSend } from '@/lib/queries/workflow'
import { DRAFT_STATUS } from '@/lib/outreach'
import type { Draft, Violation } from '@/lib/types'
import { cn } from '@/lib/utils'


/** The hook's claims against its signals: the model, cost and anything it flagged. */
function HookCheckLine({ check }: { check: Draft['hook_check'] }) {
  if (!check || check.status === 'skipped') return null
  if (check.status === 'unchecked') return <p className="text-xs text-warning-fg">Hook not checked against the signals: {check.error}</p>
  const flagged = check.claims.filter((c) => c.verdict !== 'stated').length
  const cost = `${check.model} · ${check.calls} call${check.calls === 1 ? '' : 's'}${check.duration_ms ? ` · ${Math.round(check.duration_ms / 1000)}s` : ''}`
  return (
    <p className={cn('text-xs', flagged ? 'text-danger-fg' : 'text-fg-subtle')}>
      {flagged ? `Hook check: ${flagged} claim${flagged === 1 ? '' : 's'} the signals don't state` : `Hook check: every claim is stated by a signal`} ({cost})
    </p>
  )
}

function Checks({ violations, contactFlagged = false }: { violations: Violation[]; contactFlagged?: boolean }) {
  if (violations.length === 0)
    return (
      <p data-tour="outreach-checks" className="flex items-center gap-2 rounded-md bg-success-bg px-3 py-2 text-sm text-success-fg">
        <CircleCheck className="size-4" />
        {contactFlagged ? 'The text passes every check' : 'Every check passed'}: grounded in your CV, one ask, names right, no banned phrases, under the word limit.
      </p>
    )
  return (
    <ul data-tour="outreach-checks" className="space-y-1 rounded-md border border-border bg-surface px-3 py-2">
      {violations.map((v, i) => (
        <li key={i} className={cn('flex items-start gap-2 text-sm', v.severity === 'error' ? 'text-danger-fg' : 'text-warning-fg')}>
          {v.severity === 'error' ? <CircleX className="mt-0.5 size-4 shrink-0" /> : <TriangleAlert className="mt-0.5 size-4 shrink-0" />}
          <span>{v.message}</span>
        </li>
      ))}
    </ul>
  )
}

/** Each generated sentence and what it is based on (hover for the cited items). */
function Sources({ draft }: { draft: Draft }) {
  if (draft.sentences.length === 0) return null
  return (
    <details className="rounded-md border border-border bg-surface px-3 py-2 text-sm" open={!draft.edited}>
      <summary className="cursor-default text-xs font-medium text-fg-subtle">
        Where each sentence comes from{draft.edited ? ' (as generated, before your edits)' : ''}
      </summary>
      <ul className="mt-2 space-y-1.5">
        {draft.sentences.map((s, i) => (
          <li key={i} className="flex items-start gap-2">
            <span className="flex-1">{s.text}</span>
            {s.about_job ? (
              <ToneBadge tone="gray" dot={false}>the listing</ToneBadge>
            ) : (
              s.citations.map((c) => (
                <Tooltip key={c} content={draft.citations[String(c)] ?? `item ${c}`}>
                  <span>
                    <ToneBadge tone="blue" dot={false}>
                      {(draft.citations[String(c)] ?? `#${c}`).split(' · ')[0]}
                    </ToneBadge>
                  </span>
                </Tooltip>
              ))
            )}
          </li>
        ))}
      </ul>
    </details>
  )
}

export function DraftEditor({
  draft,
  onApprove,
  onReject,
  onJobPage = false,
}: {
  draft: Draft
  onApprove: () => void
  onReject: () => void
  /** On the job page the Contact card carries the full "may have left" warning. */
  onJobPage?: boolean
}) {
  const save = useSaveDraft()
  const regenerate = useDraftRun(draft.application_id, ({ error }) => (error ? toast.error(error) : toast.success('New draft written')))
  const action = useDraftAction()
  const testSend = useTestSend()
  const queueDraft = useQueueDraft()
  const mention = useMentionApplication()
  const errors = draft.violations.filter((v) => v.severity === 'error')
  const added = draft.full_body.slice(draft.body.trim().length).trim()
  const [subject, setSubject] = useState(draft.subject)
  const [body, setBody] = useState(draft.body)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved'>('idle')
  const timer = useRef<number | undefined>(undefined)
  const editable = draft.status === 'draft'

  useEffect(() => () => window.clearTimeout(timer.current), [])

  const queueSave = (next: { subject?: string; body?: string }) => {
    setSaveState('saving')
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => {
      save.mutate(
        { id: draft.id, ...next },
        {
          onSuccess: () => setSaveState('saved'),
          onError: (e) => {
            setSaveState('idle')
            toast.error(`Couldn't save: ${e.message}`)
          },
        },
      )
    }, 700)
  }

  return (
    <div className="flex h-full flex-col">
      <div className="space-y-3 border-b border-border px-6 py-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-md font-semibold tracking-tight">
              {draft.contact ? `To ${draft.contact.full_name}` : 'No recipient'}
            </p>
            <p className="truncate text-sm text-fg-muted">
              {draft.contact?.title} · {draft.contact?.email}
            </p>
          </div>
          <ToneBadge tone={DRAFT_STATUS[draft.status].tone}>{DRAFT_STATUS[draft.status].label}</ToneBadge>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-fg-muted">
          <Link
            to={`/jobs/${draft.job_id}`}
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-bg-subtle px-2 py-1 hover:border-border-strong"
          >
            <FitBadge fit={draft.fit} size="sm" />
            <span className="font-medium text-fg">{draft.job_title}</span>
            <span>· {draft.company_name}</span>
          </Link>
          {draft.cv_version && (
            <Link
              to={`/jobs/${draft.job_id}/cv`}
              className="inline-flex items-center gap-1.5 rounded-md border border-border bg-bg-subtle px-2 py-1 hover:border-border-strong"
            >
              <FileText className="size-3.5" />
              CV v{draft.cv_version} attached
            </Link>
          )}
          <Tooltip
            content={
              draft.generated_via === 'claude -p'
                ? `Claude Code headless (claude -p)${draft.auth ? `, auth: ${draft.auth === 'none' ? 'your subscription' : draft.auth}` : ''}. Emails never use the local model.`
                : 'Sample drafter (no model call)'
            }
          >
            <span className="ml-auto" data-tour="outreach-model">
              {draft.edited ? 'Edited by you · ' : ''}Drafted by {draft.model}
              {draft.generated_via === 'claude -p' ? ' via claude -p' : ''}
              {draft.auth === 'none' ? ' · subscription' : ''} · {relativeTime(draft.created_at)}
            </span>
          </Tooltip>
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-5">
        {draft.status === 'draft' && draft.contact && onJobPage && draft.contact_alerts.length > 0 && (
          <p role="alert" className="flex items-center gap-2 rounded-md border border-tone-red-border bg-danger-bg px-3 py-2 text-sm text-danger-fg">
            <TriangleAlert className="size-4 shrink-0" />
            {draft.contact.full_name} may have left {draft.company_name}: see Contact before approving.
          </p>
        )}
        {draft.status === 'draft' && draft.contact && !onJobPage && (
          <ContactAlertBanner
            alerts={draft.contact_alerts}
            nextContact={draft.next_contact}
            appId={draft.application_id}
            contactId={draft.contact.id}
            contactName={draft.contact.full_name}
            companyName={draft.company_name}
            jobId={draft.job_id}
          />
        )}
        {draft.status === 'draft' && <Checks violations={draft.violations} contactFlagged={draft.contact_alerts.length > 0} />}
        {draft.format === 'intro' && (
          <div className="space-y-1.5 rounded-md border border-border bg-surface px-3 py-2 text-sm" data-tour="outreach-signals">
            <p className="text-xs font-medium text-fg-subtle">
              {draft.needs_signal ? 'Needs a signal: pick or add one about the company on its page, then Regenerate' : 'Company facts in the hook (verified signals)'}
            </p>
            {draft.research_note && <p className="text-xs text-warning-fg">Research: {draft.research_note}</p>}
            {draft.signals.map((s) => (
              <p key={s.id} className="flex items-start gap-2">
                <span className="flex-1">{s.fact}</span>
                {s.source_url && (
                  <a href={s.source_url} target="_blank" rel="noreferrer" className="shrink-0 text-xs text-primary hover:underline">
                    source
                  </a>
                )}
              </p>
            ))}
            <HookCheckLine check={draft.hook_check} />
            {draft.name_source && (
              <Tooltip content={`“${draft.name_source.excerpt}”`}>
                <p className="text-xs text-fg-subtle">
                  Greeting spells it “{draft.name_source.first_name}”, as on{' '}
                  <a href={draft.name_source.url} target="_blank" rel="noreferrer" className="text-primary hover:underline">
                    {draft.name_source.title || draft.name_source.url.replace(/^https?:\/\/(www\.)?/, '').slice(0, 40)}
                  </a>
                </p>
              </Tooltip>
            )}
          </div>
        )}
        <div className="space-y-1.5">
          <Label htmlFor="subject">Subject</Label>
          <Input
            id="subject"
            value={subject}
            readOnly={!editable}
            onChange={(e) => {
              setSubject(e.target.value)
              queueSave({ subject: e.target.value })
            }}
            className="h-9 text-base font-medium"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="body">Message</Label>
          <Textarea
            id="body"
            value={body}
            readOnly={!editable}
            onChange={(e) => {
              setBody(e.target.value)
              queueSave({ body: e.target.value })
            }}
            className="field-sizing-content min-h-48 text-base leading-7"
          />
          {draft.application_mention && (draft.status === 'draft' || draft.status === 'approved') && (
            <label className="flex items-center gap-2 pt-1 text-sm text-fg-muted">
              <Checkbox
                checked={draft.mention_included}
                disabled={mention.isPending}
                onCheckedChange={(v) =>
                  mention.mutate(
                    { id: draft.id, include: v === true },
                    { onError: (e) => toast.error(e.message) },
                  )
                }
                aria-label="Mention my web application"
              />
              Mention my web application: “{draft.application_mention}”
            </label>
          )}
        </div>
        {added && (
          <div className="space-y-1.5">
            <Label>Added when sent (Settings → Email)</Label>
            <p className="rounded-md border border-dashed border-border-strong px-3 py-2 text-sm whitespace-pre-line text-fg-muted">{added}</p>
          </div>
        )}
        <Sources draft={draft} />
        {draft.test_sent_at && (
          <p className="text-xs text-fg-subtle">Test sent to you {relativeTime(draft.test_sent_at)}</p>
        )}
      </div>

      <div className="flex h-14 shrink-0 items-center gap-2 border-t border-border px-6">
        <span className="text-xs text-fg-subtle">
          {editable
            ? saveState === 'saving'
              ? 'Saving…'
              : saveState === 'saved'
                ? 'All changes saved'
                : 'Edits autosave'
            : draft.status === 'rejected'
              ? 'Rejected drafts are kept for reference'
              : 'This email has left review'}
        </span>
        <div className="ml-auto flex items-center gap-2">
          {editable && (
            <>
              <Button variant="ghost" onClick={onReject}>
                <X />
                Reject
                <Kbd>R</Kbd>
              </Button>
              <CritiqueButton kind="email" id={draft.id} />
              <Button
                onClick={() => regenerate.start(undefined, { onError: (e) => toast.error(e.message) })}
                disabled={regenerate.running}
              >
                <RefreshCw className={regenerate.running ? 'animate-spin' : undefined} />
                {regenerate.running ? 'Drafting…' : 'Regenerate'}
              </Button>
              <Button
                data-tour="outreach-test-send"
                onClick={() =>
                  testSend.mutate(draft.id, {
                    onSuccess: (log) => toast.success('Test email sent', { description: `To ${log.to}, with the CV attached. Check your inbox.` }),
                    onError: (e) => toast.error(e.message),
                  })
                }
                disabled={testSend.isPending}
              >
                <Send />
                {testSend.isPending ? 'Sending…' : 'Send test to me'}
              </Button>
              <Tooltip
                content={
                  draft.contact_alerts.length
                    ? `${draft.contact?.full_name ?? 'The contact'} may have left: write to someone else or verify them first`
                    : errors.length
                      ? `Fix ${errors.length} problem${errors.length > 1 ? 's' : ''} first`
                      : null
                }
              >
                <span>
                  <Button variant="default" onClick={onApprove} data-tour="outreach-approve" disabled={errors.length > 0 || draft.contact_alerts.length > 0}>
                    <CircleCheck />
                    Approve
                    <Kbd className="border-transparent bg-primary-hover text-primary-fg">A</Kbd>
                  </Button>
                </span>
              </Tooltip>
            </>
          )}
          {draft.status === 'rejected' && (
            <Button
              onClick={() =>
                action.mutate(
                  { id: draft.id, action: 'restore' },
                  { onSuccess: () => toast.success('Moved back to review') },
                )
              }
            >
              <RotateCcw />
              Restore to review
            </Button>
          )}
          {draft.status === 'approved' && (
            <Button
              variant="default"
              data-tour="outreach-queue-add"
              onClick={() =>
                queueDraft.mutate(draft.id, {
                  onSuccess: () => toast.success('Added to the send queue', { description: `To ${draft.contact?.full_name} · ${draft.company_name}` }),
                  onError: (e) => toast.error(e.message),
                })
              }
              disabled={queueDraft.isPending}
            >
              <ListPlus />
              Add to send queue
            </Button>
          )}
          {(draft.status === 'queued' || draft.status === 'sent') && (
            <Button asChild>
              <Link to="/outreach?tab=queue">
                <Mail />
                View send queue
              </Link>
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

