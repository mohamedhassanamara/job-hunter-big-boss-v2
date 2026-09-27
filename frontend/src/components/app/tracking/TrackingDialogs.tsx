import { type ReactNode, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { useLogInterview, useLogResponse, useMarkApplied } from '@/lib/queries/tracking'
import { INTERVIEW_TYPE_LABELS, localIso, METHOD_LABELS, RESPONSE_LABELS, todayIso } from '@/lib/tracking'
import type { ApplyMethod, InterviewType, ResponseKind } from '@/lib/types'

export interface TrackTarget {
  appId: number
  title: string
  company: string
}

function Shell({
  open,
  onOpenChange,
  title,
  subtitle,
  children,
  footer,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  subtitle: string
  children: ReactNode
  footer: ReactNode
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={title} className="max-w-md p-0">
        <div className="border-b border-border px-5 py-4">
          <h2 className="text-md font-semibold tracking-tight">{title}</h2>
          <p className="truncate text-sm text-fg-muted">{subtitle}</p>
        </div>
        <div className="space-y-4 px-5 py-4">{children}</div>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">{footer}</div>
      </DialogContent>
    </Dialog>
  )
}

function Field({ label, htmlFor, children, hint }: { label: string; htmlFor?: string; children: ReactNode; hint?: string }) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {hint && <p className="text-xs text-fg-subtle">{hint}</p>}
    </div>
  )
}

const options = <T extends string>(labels: Record<T, string>) =>
  (Object.keys(labels) as T[]).map((value) => ({ value, label: labels[value] }))

/** Records the date, method and the CV version sent. That version is locked from then on. */
export function MarkAppliedDialog({
  target,
  cvVersion,
  cvVersionId,
  onOpenChange,
  onDone,
}: {
  target: TrackTarget | null
  cvVersion: number | null
  cvVersionId?: number
  onOpenChange: (open: boolean) => void
  onDone?: () => void
}) {
  const [date, setDate] = useState(todayIso())
  const [method, setMethod] = useState<ApplyMethod>('company_site')
  const [notes, setNotes] = useState('')
  const mark = useMarkApplied()
  const submit = () => {
    if (!target) return
    mark.mutate(
      { appId: target.appId, applied_on: date, method, cv_version_id: cvVersionId, notes },
      {
        onSuccess: () => {
          toast.success('Marked applied', { description: `${target.title} · CV v${cvVersion ?? '?'} locked` })
          onOpenChange(false)
          onDone?.()
        },
        onError: (e) => toast.error(e.message),
      },
    )
  }
  return (
    <Shell
      open={!!target}
      onOpenChange={onOpenChange}
      title="Mark applied"
      subtitle={target ? `${target.title} · ${target.company}` : ''}
      footer={
        <>
          <Button size="sm" variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button size="sm" variant="default" onClick={submit} disabled={!date || mark.isPending}>
            Mark applied
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-2 gap-3">
        <Field label="Applied on" htmlFor="applied-on">
          <Input id="applied-on" type="date" value={date} max={todayIso()} onChange={(e) => setDate(e.target.value)} />
        </Field>
        <Field label="Method">
          <Select aria-label="Method" value={method} onValueChange={(v) => setMethod(v as ApplyMethod)} options={options(METHOD_LABELS)} className="w-full" />
        </Field>
      </div>
      <Field label="CV sent" hint="This version is locked: later edits create a new version.">
        <p className="text-sm">{cvVersion ? `Approved CV v${cvVersion}` : 'Latest approved CV'}</p>
      </Field>
      <Field label="Notes" htmlFor="applied-notes">
        <Textarea id="applied-notes" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Referral, portal account, cover letter…" className="min-h-16" />
      </Field>
    </Shell>
  )
}

export function LogReplyDialog({
  target,
  onOpenChange,
  onLogged,
}: {
  target: TrackTarget | null
  onOpenChange: (open: boolean) => void
  onLogged?: (kind: ResponseKind) => void
}) {
  const [kind, setKind] = useState<ResponseKind>('positive')
  const [date, setDate] = useState(todayIso())
  const [notes, setNotes] = useState('')
  const log = useLogResponse()
  const submit = () => {
    if (!target) return
    log.mutate(
      { appId: target.appId, kind, received_on: date, notes },
      {
        onSuccess: () => {
          onOpenChange(false)
          onLogged?.(kind)
        },
        onError: (e) => toast.error(e.message),
      },
    )
  }
  return (
    <Shell
      open={!!target}
      onOpenChange={onOpenChange}
      title="Log reply"
      subtitle={target ? `${target.title} · ${target.company}` : ''}
      footer={
        <>
          <Button size="sm" variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button size="sm" variant="default" onClick={submit} disabled={!date || log.isPending}>
            Log reply
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-2 gap-3">
        <Field label="Reply">
          <Select aria-label="Reply" value={kind} onValueChange={(v) => setKind(v as ResponseKind)} options={options(RESPONSE_LABELS)} className="w-full" />
        </Field>
        <Field label="Received on" htmlFor="reply-on">
          <Input id="reply-on" type="date" value={date} max={todayIso()} onChange={(e) => setDate(e.target.value)} />
        </Field>
      </div>
      <Field label="Notes" htmlFor="reply-notes">
        <Textarea id="reply-notes" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Who replied, what they asked…" className="min-h-16" />
      </Field>
    </Shell>
  )
}

function defaultInterviewTime(): string {
  const d = new Date()
  d.setDate(d.getDate() + 1)
  return `${localIso(d)}T10:00`
}

export function LogInterviewDialog({
  target,
  round,
  onOpenChange,
}: {
  target: TrackTarget | null
  round: number
  onOpenChange: (open: boolean) => void
}) {
  const [when, setWhen] = useState(defaultInterviewTime())
  const [type, setType] = useState<InterviewType>(round <= 1 ? 'hr' : 'technical')
  const [notes, setNotes] = useState('')
  const log = useLogInterview()
  const submit = () => {
    if (!target) return
    log.mutate(
      { appId: target.appId, scheduled_at: new Date(when).toISOString(), type, notes },
      {
        onSuccess: (i) => {
          toast.success(`Interview round ${i.round} logged`, { description: target.title })
          onOpenChange(false)
        },
        onError: (e) => toast.error(e.message),
      },
    )
  }
  return (
    <Shell
      open={!!target}
      onOpenChange={onOpenChange}
      title={`Log interview · round ${round}`}
      subtitle={target ? `${target.title} · ${target.company}` : ''}
      footer={
        <>
          <Button size="sm" variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button size="sm" variant="default" onClick={submit} disabled={!when || log.isPending}>
            Log interview
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-2 gap-3">
        <Field label="When" htmlFor="interview-at">
          <Input id="interview-at" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />
        </Field>
        <Field label="Type">
          <Select aria-label="Type" value={type} onValueChange={(v) => setType(v as InterviewType)} options={options(INTERVIEW_TYPE_LABELS)} className="w-full" />
        </Field>
      </div>
      <Field label="Notes" htmlFor="interview-notes">
        <Textarea id="interview-notes" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Interviewers, format, what to prepare…" className="min-h-16" />
      </Field>
    </Shell>
  )
}
