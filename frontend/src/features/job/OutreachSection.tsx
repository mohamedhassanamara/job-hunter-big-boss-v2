import { ArrowRight, CircleCheck, Clock, FileText, Mail, Search, Send, Sparkles, UserPlus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { ContactTierBadge } from '@/components/app/badges'
import { NewContactDialog } from '@/components/app/NewContactDialog'
import { DraftEditor } from '@/components/app/outreach/DraftEditor'
import { Section } from '@/components/app/PageHeader'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { clockTime, relativeTime } from '@/lib/format'
import { usePatchApplication, useQueueLookup } from '@/lib/queries/jobs'
import { useCompany, useSetJobContact } from '@/lib/queries/library'
import { useDraftAction, useGenerateDraft, useOutreachStep, useSentManually } from '@/lib/queries/workflow'
import { todayIso } from '@/lib/tracking'
import type { JobDetail, OutreachStepName } from '@/lib/types'
import { cn } from '@/lib/utils'

const STEPS: { key: OutreachStepName[]; label: string }[] = [
  { key: ['contact'], label: 'Contact' },
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

function FindContact({ job }: { job: JobDetail }) {
  const company = useCompany(job.company.id)
  const lookup = useQueueLookup()
  const set = useSetJobContact()
  const [adding, setAdding] = useState(false)
  const people = company.data?.contacts ?? []
  return (
    <div className="space-y-3 p-4">
      <div className="flex items-center gap-2 text-sm">
        <ContactTierBadge tier={job.application.contact_tier} />
        <span className="text-fg-muted">
          {job.lookup_status === 'queued'
            ? `${job.company.name} is in the Apollo lookup queue.`
            : job.lookup_status === 'not_found'
              ? 'The Apollo lookup found nobody.'
              : `Nobody at ${job.company.name} yet.`}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {job.lookup_status !== 'queued' && (
          <Button
            size="sm"
            variant="default"
            onClick={() => lookup.mutate(job.application.id, { onSuccess: () => toast.success('Queued for an Apollo lookup'), onError: (e) => toast.error(e.message) })}
            disabled={lookup.isPending}
          >
            <Search />
            Find contact
          </Button>
        )}
        {job.lookup_status === 'queued' && (
          <Button size="sm" asChild>
            <Link to="/contacts?tab=lookups">
              Open the lookup queue
              <ArrowRight />
            </Link>
          </Button>
        )}
        {people.length > 0 && (
          <Select
            size="sm"
            aria-label="Pick a contact"
            placeholder="Pick a contact"
            value={undefined}
            onValueChange={(v) => set.mutate({ appId: job.application.id, contactId: Number(v) }, { onSuccess: () => toast.success('Contact set'), onError: (e) => toast.error(e.message) })}
            options={people.map((c) => ({ value: String(c.id), label: `${c.full_name}${c.title ? ` · ${c.title}` : ''}` }))}
            className="w-64"
          />
        )}
        <Button size="sm" variant="ghost" onClick={() => setAdding(true)}>
          <UserPlus />
          Add a contact
        </Button>
      </div>
      <NewContactDialog
        key={`add-${adding}`}
        open={adding}
        title={`Add a contact at ${job.company.name}`}
        submitLabel="Add and use"
        pending={set.isPending}
        onOpenChange={setAdding}
        onSubmit={(contact) =>
          set.mutate({ appId: job.application.id, contact }, { onSuccess: () => { toast.success(`Writing to ${contact.full_name}`); setAdding(false) }, onError: (e) => toast.error(e.message) })
        }
      />
    </div>
  )
}

/** The cold-email route on the Job page: the next action is always visible. */
export function OutreachSection({ job }: { job: JobDetail }) {
  const app = job.application
  const { data, isPending } = useOutreachStep(app.id)
  const generate = useGenerateDraft()
  const action = useDraftAction()
  const patch = usePatchApplication()
  const [sentMyself, setSentMyself] = useState(false)
  const route = app.effective_route
  const ready = !isPending && !!data
  // Arriving from the Pipeline or Today with #outreach: bring the section into view.
  useEffect(() => {
    if (ready && window.location.hash === '#outreach') {
      document.getElementById('outreach')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [ready])

  if (route !== 'cold_email') {
    if (!job.contact || ['done', 'interview', 'closed'].includes(app.stage)) return null
    return (
      <div className="flex items-center gap-3 rounded-lg border border-tone-blue-border bg-info-bg p-4 text-sm">
        <Mail className="size-4 text-info-fg" />
        <span className="flex-1 text-info-fg">A contact was found ({job.contact.full_name}). Switch this job to a cold email?</span>
        <Button
          size="sm"
          onClick={() => patch.mutate({ id: app.id, patch: { route: 'cold_email' } }, { onSuccess: () => toast.success('Route set to cold email'), onError: (e) => toast.error(e.message) })}
        >
          Switch to cold email
        </Button>
      </div>
    )
  }
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
      title="Cold email"
      action={
        <span className="flex items-center gap-2 text-xs text-fg-subtle">
          {job.contact ? `To ${job.contact.full_name}` : 'No contact yet'}
          {data.step === 'contact' && <TourButton tour="email-route" label="How it works" />}
        </span>
      }
    >
      <div data-tour="job-outreach">
        <Stepper step={data.step} />
        {data.step === 'contact' && <FindContact job={job} />}
        {data.step === 'cv' && (
          <div className="flex items-center gap-3 p-4 text-sm">
            <FileText className="size-4 text-fg-subtle" />
            <span className="flex-1 text-fg-muted">The email is written from your approved CV and attaches it. Approve the CV first.</span>
            <Button size="sm" variant="default" asChild>
              <Link to={`/jobs/${job.id}/cv`}>Open CV Studio</Link>
            </Button>
          </div>
        )}
        {data.step === 'draft' && (
          <div className="flex items-center gap-3 p-4 text-sm">
            <Sparkles className="size-4 text-fg-subtle" />
            <span className="flex-1 text-fg-muted">
              Contact and CV v{data.cv_version} ready. Claude drafts a short email from your CV; you review everything before it goes anywhere.
              {!data.has_email && ' The contact has no email address yet.'}
            </span>
            <Button
              size="sm"
              variant="default"
              disabled={generate.isPending || !data.has_email}
              onClick={() => generate.mutate(app.id, { onSuccess: () => toast.success('Email drafted: review it below'), onError: (e) => toast.error(e.message) })}
            >
              <Sparkles className={generate.isPending ? 'animate-pulse' : undefined} />
              {generate.isPending ? 'Drafting…' : 'Draft email with AI'}
            </Button>
          </div>
        )}
        {draft && ['review', 'queue'].includes(data.step) && (
          <div className="h-160 border-b border-border">
            <DraftEditor key={`${draft.id}-${draft.updated_at}`} draft={draft} onApprove={() => decide('approve')} onReject={() => decide('reject')} />
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
          <div className="flex justify-end px-4 py-2">
            <Button size="xs" variant="ghost" onClick={() => setSentMyself(true)}>
              <Send />
              I sent it myself
            </Button>
          </div>
        )}
      </div>
      <SentMyselfDialog key={`sent-${sentMyself}`} appId={app.id} open={sentMyself} onOpenChange={setSentMyself} />
    </Section>
  )
}
