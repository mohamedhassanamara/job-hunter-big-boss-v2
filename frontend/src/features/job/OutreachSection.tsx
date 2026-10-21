import { ArrowRight, CircleCheck, Clock, ClipboardCopy, Download, FileText, LoaderCircle, Send, Sparkles, TriangleAlert } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { GetContactPanel } from '@/components/app/contact/GetContactPanel'
import { GenerationFailed } from '@/components/app/GenerationFailed'
import { DraftEditor } from '@/components/app/outreach/DraftEditor'
import { ExternalAIDialog } from '@/components/app/outreach/ExternalAIDialog'
import { UnverifiedBadge } from '@/components/app/outreach/ApproveUnverifiedDialog'
import { PasteDescriptionDialog } from '@/components/app/PasteDescriptionDialog'
import { Section } from '@/components/app/PageHeader'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { clockTime, relativeTime } from '@/lib/format'
import { useDraftAction, useDraftRun, useFetchFullListing, useOutreachStep, useSentManually } from '@/lib/queries/workflow'
import { DraftProgressLine } from '@/components/app/outreach/DraftProgressLine'
import { todayIso } from '@/lib/tracking'
import type { EmailMode, JobDetail, OutreachStep, OutreachStepName } from '@/lib/types'
import { cn } from '@/lib/utils'

const STEPS: { key: OutreachStepName[]; label: string }[] = [
  { key: ['get_contact', 'verify_contact'], label: 'Get contact' },
  { key: ['cv', 'draft'], label: 'Draft' },
  { key: ['review'], label: 'Review' },
  { key: ['queue', 'queued'], label: 'Send queue' },
  { key: ['sent'], label: 'Sent' },
]

function Stepper({ step }: { step: OutreachStepName }) {
  const current = STEPS.findIndex((s) => s.key.includes(step))
  return (
    <ol className="flex items-center gap-2 border-b border-border px-4 py-2.5 text-xs">
      {STEPS.map((s, i) => (
        <li key={s.label} className="flex items-center gap-2">
          <span
            className={cn(
              'flex size-5 items-center justify-center rounded-full border text-2xs font-semibold',
              i < current ? 'border-primary bg-primary text-primary-fg' : i === current ? 'border-primary text-primary' : 'border-border-strong text-fg-subtle',
            )}
          >
            {i < current ? '✓' : i + 1}
          </span>
          <span className={cn(i === current ? 'font-medium text-fg' : 'text-fg-muted')}>{s.label}</span>
          {i < STEPS.length - 1 && <span className="h-px w-6 bg-border-strong" />}
        </li>
      ))}
    </ol>
  )
}

function SentMyselfDialog({ appId, open, onOpenChange }: { appId: number; open: boolean; onOpenChange: (o: boolean) => void }) {
  const [date, setDate] = useState(todayIso())
  const sent = useSentManually()
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="I sent it myself" className="max-w-sm p-0">
        <div className="space-y-3 px-5 py-4">
          <h2 className="text-md font-semibold tracking-tight">I sent it myself</h2>
          <p className="text-sm text-fg-muted">The approved email is recorded as sent: the job moves to Sent, the CV is locked, and follow-up reminders start.</p>
          <Input type="date" value={date} max={todayIso()} onChange={(e) => setDate(e.target.value)} aria-label="Sent on" />
        </div>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
          <Button size="sm" variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            size="sm"
            variant="default"
            disabled={sent.isPending}
            onClick={() =>
              sent.mutate(
                { appId, sent_on: date },
                { onSuccess: () => { toast.success('Recorded as sent'); onOpenChange(false) }, onError: (e) => toast.error(e.message) },
              )
            }
          >
            Mark as sent
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

const MODES: { value: EmailMode; label: string; hint: string }[] = [
  { value: 'applied', label: 'Application follow-up', hint: 'You applied (or are applying): a short, honest email with your best proof and any requirement you do not meet. No research.' },
  { value: 'speculative', label: 'Speculative email', hint: 'No posting: the company is researched first, then a short introduction from its signals asks about an opening.' },
]

/** The draft step's two choices: which email to write, and the full listing when only a snippet is stored. */
function DraftChoices({ jobId, data, mode, onMode }: { jobId: number; data: OutreachStep; mode: EmailMode; onMode: (m: EmailMode) => void }) {
  const fetchFull = useFetchFullListing()
  const [pasting, setPasting] = useState(false)
  const runFetch = () =>
    fetchFull.mutate(jobId, {
      onSuccess: (r) => {
        if (r.ok) toast.success(r.message, { description: `${r.characters.toLocaleString()} characters` })
        else if (r.can_paste) toast(r.message, { action: { label: 'Paste it', onClick: () => setPasting(true) }, duration: 10000 })
        else toast.error(r.message)
      },
      onError: (e) => toast.error(e.message),
    })
  return (
    <div className="space-y-3">
      <div className="space-y-1.5" data-tour="outreach-mode">
        <div role="radiogroup" aria-label="Email type" className="flex gap-1.5">
          {MODES.map((m) => (
            <Button key={m.value} size="sm" variant={mode === m.value ? 'outline' : 'ghost'} role="radio" aria-checked={mode === m.value} onClick={() => onMode(m.value)}>
              {m.label}
            </Button>
          ))}
        </div>
        <p className="text-xs text-fg-subtle">{MODES.find((m) => m.value === mode)?.hint}</p>
      </div>
      {mode === 'applied' && data.listing_short && (
        <div className="flex items-start gap-2 rounded-md border border-border bg-warning-bg px-3 py-2 text-sm" data-tour="outreach-listing">
          <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warning-fg" />
          <div className="min-w-0 flex-1 space-y-1.5">
            <p className="font-medium text-warning-fg">Listing is a short snippet: paste the full description or fetch it</p>
            <p className="text-xs text-fg-muted">
              Only {data.listing_chars.toLocaleString()} characters are saved. You can draft without it, but constraints like residency or a language requirement can't be detected. Saving the full text rescores the job.
            </p>
            <div className="flex gap-1.5">
              {data.can_fetch_listing && (
                <Button size="xs" variant="ghost" onClick={runFetch} disabled={fetchFull.isPending}>
                  {fetchFull.isPending ? <LoaderCircle className="animate-spin" /> : <Download />}
                  Fetch it
                </Button>
              )}
              <Button size="xs" variant="ghost" onClick={() => setPasting(true)}>
                Paste description
              </Button>
            </div>
          </div>
        </div>
      )}
      <PasteDescriptionDialog jobId={jobId} open={pasting} onClose={() => setPasting(false)} />
    </div>
  )
}

/** The cold-email route on the Job page: the next action is always visible. */
export function OutreachSection({ job }: { job: JobDetail }) {
  const app = job.application
  const { data, isPending } = useOutreachStep(app.id)
  const run = useDraftRun(app.id, ({ error }) => (error ? toast.error(error) : toast.success('Email drafted: review it below')))
  const autoStarted = useRef(false)
  const action = useDraftAction()
  const [sentMyself, setSentMyself] = useState(false)
  const [pickedMode, setPickedMode] = useState<EmailMode | null>(null)
  const [externalOpen, setExternalOpen] = useState(false)
  const ready = !isPending && !!data
  // The model didn't answer (this run, or a background draft): Retry / Generate with Claude.
  const emailTask = app.tracks.generation?.email
  const failedMessage = run.state?.status === 'failed' && run.state.generation_failed ? (run.state.error ?? 'The model did not answer.') : emailTask?.status === 'failed' ? (emailTask.error ?? 'The model did not answer.') : null
  // Arriving from the Pipeline or Today with #outreach: bring the section into view.
  useEffect(() => {
    if (ready && window.location.hash === '#outreach') {
      document.getElementById('outreach')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [ready])

  // From the Pipeline (drop on Ready) or CV Studio: ?draft=1 starts the draft step once.
  useEffect(() => {
    if (!ready || autoStarted.current || data?.step !== 'draft' || !data.has_email) return
    const params = new URLSearchParams(window.location.search)
    if (params.get('draft') !== '1') return
    autoStarted.current = true
    params.delete('draft')
    window.history.replaceState(null, '', `${window.location.pathname}${params.size ? `?${params}` : ''}${window.location.hash}`)
    run.start(undefined, { onError: (e) => toast.error(e.message) })
  }, [ready, data?.step, data?.has_email, run])

  if (app.stage === 'new' || (app.stage === 'closed' && ['no_contact', 'verify', 'contact'].includes(app.tracks.outreach))) return null
  if (isPending || !data) return <Skeleton className="h-40" />

  const draft = data.draft
  const decide = (verdict: 'approve' | 'reject') =>
    draft &&
    action.mutate(
      { id: draft.id, action: verdict },
      {
        onSuccess: () => toast.success(verdict === 'approve' ? 'Approved: ready to send' : 'Draft rejected'),
        onError: (e) => toast.error(e.message),
      },
    )

  return (
    <Section
      title="Outreach"
      action={
        <span className="flex items-center gap-2 text-xs text-fg-subtle">
          {job.contact ? `To ${job.contact.full_name}` : 'No contact yet'}
          <Button size="xs" variant="ghost" onClick={() => setExternalOpen(true)} data-tour="outreach-external">
            <ClipboardCopy />
            Copy for another AI
          </Button>
          {(data.step === 'get_contact' || data.step === 'verify_contact') && <TourButton tour="get-contact" label="How it works" />}
        </span>
      }
    >
      <div data-tour="job-outreach">
        <Stepper step={data.step} />
        {(data.step === 'get_contact' || data.step === 'verify_contact') && (
          <div className="space-y-2 p-4">
            <p className="text-xs text-fg-subtle">
              The email waits for a verified contact (research too).{' '}
              <Link to={`/outreach?tab=contacts&app=${app.id}`} className="text-primary hover:underline">
                Work through Contacts to get
              </Link>
            </p>
            <GetContactPanel appId={app.id} />
          </div>
        )}
        {data.step === 'cv' && (
          <div className="flex items-center gap-3 p-4 text-sm">
            <FileText className="size-4 text-fg-subtle" />
            <span className="flex-1 text-fg-muted">The email is written from your approved CV and attaches it. Approve the CV first.</span>
            <Button size="sm" asChild>
              <Link to={`/jobs/${job.id}/cv`}>Open CV Studio</Link>
            </Button>
          </div>
        )}
        {data.step === 'draft' && failedMessage && !run.running && (
          <GenerationFailed
            what="email"
            message={failedMessage}
            onRetry={() => run.start({ mode: pickedMode ?? data.email_mode }, { onError: (e) => toast.error(e.message) })}
            onClaude={() => run.start({ mode: pickedMode ?? data.email_mode, use: 'claude' }, { onError: (e) => toast.error(e.message) })}
          />
        )}
        {data.step === 'draft' && (
          <div className="space-y-3 p-4 text-sm">
            <div className="flex items-center gap-3">
              <Sparkles className="size-4 text-fg-subtle" />
              <span className="flex-1 text-fg-muted">
                {job.contact ? `${job.contact.full_name} (verified)` : 'Contact'} and CV v{data.cv_version} ready. The model set in Settings → Models writes the email from your approved CV; you review everything before it goes anywhere.
                {!data.has_email && ' The contact has no email address yet.'}
              </span>
              {run.running ? (
                <DraftProgressLine state={run.state} />
              ) : (
                <Button size="sm" disabled={!data.has_email} onClick={() => run.start({ mode: pickedMode ?? data.email_mode }, { onError: (e) => toast.error(e.message) })}>
                  <Sparkles />
                  Draft email with AI
                </Button>
              )}
            </div>
            {!run.running && <DraftChoices jobId={job.id} data={data} mode={pickedMode ?? data.email_mode} onMode={setPickedMode} />}
          </div>
        )}
        {draft && ['review', 'queue'].includes(data.step) && (
          <div className="h-160 border-b border-border">
            <DraftEditor key={`${draft.id}-${draft.updated_at}`} draft={draft} onApprove={() => decide('approve')} onReject={() => decide('reject')} onJobPage approving={action.isPending && action.variables?.action === 'approve'} />
          </div>
        )}
        {data.step === 'queued' && (
          <div className="flex items-center gap-3 p-4 text-sm">
            <Clock className="size-4 text-fg-subtle" />
            <span className="flex-1">
              #{data.queue_position} in the send queue ·{' '}
              {data.queue_eta ? (
                <span>sends around {clockTime(data.queue_eta)}</span>
              ) : (
                <span className="text-fg-muted">the queue is {data.queue_status}: it sends once you start it</span>
              )}
            </span>
            <Button size="sm" asChild>
              <Link to="/outreach?tab=queue">
                Open send queue
                <ArrowRight />
              </Link>
            </Button>
          </div>
        )}
        {data.step === 'sent' && (
          <div className="flex items-center gap-3 p-4 text-sm">
            <CircleCheck className="size-4 text-success-dot" />
            <span className="flex-1">
              Sent {relativeTime(data.sent_at)} to {job.contact?.full_name ?? 'the contact'}. Follow-ups, replies and interviews are tracked below.
            </span>
          </div>
        )}
        {(data.step === 'queue' || data.step === 'queued') && (
          <div className="flex items-center justify-between gap-2 px-4 py-2">
            {data.draft?.unverified_approval ? <UnverifiedBadge at={data.draft.unverified_approval.at} ignored={data.draft.unverified_approval.ignored.length} /> : <span />}
            <Button size="xs" variant="ghost" onClick={() => setSentMyself(true)}>
              <Send />
              I sent it myself
            </Button>
          </div>
        )}
      </div>
      <SentMyselfDialog key={`sent-${sentMyself}`} appId={app.id} open={sentMyself} onOpenChange={setSentMyself} />
      <ExternalAIDialog appId={app.id} open={externalOpen} onClose={() => setExternalOpen(false)} defaultMode={data.email_mode} />
    </Section>
  )
}
