import { ClipboardPaste, Copy, ExternalLink, Search, Sparkles, TriangleAlert, Undo2, UserPlus, X } from 'lucide-react'
import { CritiqueButton } from '@/components/app/CritiqueButton'
import { useRef, useState } from 'react'
import { toast } from 'sonner'
import { ToneBadge, type Tone } from '@/components/app/badges'
import { Section } from '@/components/app/PageHeader'
import { ErrorState } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input, Textarea } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip } from '@/components/ui/tooltip'
import { relativeTime } from '@/lib/format'
import { LINKEDIN_TRACK } from '@/lib/linkedin'
import { useParsePaste } from '@/lib/queries/getContact'
import { useAddLinkedInPerson, useDraftLinkedIn, useEditLinkedIn, useLinkedInPanel, useLinkedInStatus, useRemoveLinkedInPerson } from '@/lib/queries/linkedin'
import type { JobDetail, LinkedInGroup, LinkedInPanel, LinkedInPerson } from '@/lib/types'
import { cn } from '@/lib/utils'

const GROUP: Record<LinkedInGroup, { label: string; tone: Tone }> = {
  hiring_team: { label: 'Hiring team', tone: 'violet' },
  alumni: { label: 'Alumni', tone: 'teal' },
  lead: { label: 'Team lead', tone: 'blue' },
  recruiter: { label: 'Recruiter', tone: 'slate' },
  other: { label: 'Other', tone: 'gray' },
}

/** The note's angle: detected from the title unless you pick one. */
const ANGLES: { value: string; label: string }[] = [
  { value: 'auto', label: 'Detect from title' },
  ...(['recruiter', 'lead', 'alumni', 'other'] as const).map((g) => ({ value: g, label: GROUP[g].label })),
]

function AddPerson({ appId, group, school, onDone }: { appId: number; group: LinkedInGroup; school: string | null; onDone: () => void }) {
  const add = useAddLinkedInPerson(appId)
  const parse = useParsePaste()
  const hiring = group === 'hiring_team'
  const [f, setF] = useState({ full_name: '', title: '', linkedin_url: '', group: hiring || group === 'other' ? 'auto' : (group as string), alumni: group === 'alumni' })
  const fill = (text: string) =>
    text.trim() &&
    parse.mutate(text, {
      onSuccess: (p) => setF((x) => ({ ...x, full_name: p.full_name ?? x.full_name, title: p.title ?? x.title, linkedin_url: p.linkedin_url ?? x.linkedin_url })),
    })
  return (
    <form
      className="space-y-2 rounded-md border border-border bg-bg-subtle p-3"
      onSubmit={(e) => {
        e.preventDefault()
        add.mutate({ ...f, group: f.group === 'auto' ? null : (f.group as LinkedInGroup), hiring_team: hiring }, { onSuccess: () => (toast.success(`${f.full_name} added`), onDone()), onError: (err) => toast.error(err.message) })
      }}
    >
      <Textarea onPaste={(e) => fill(e.clipboardData.getData('text'))} placeholder="Paste their LinkedIn profile header (name, title, URL): the fields fill in" className="min-h-12 text-xs" aria-label="Paste a profile" />
      <div className="grid grid-cols-3 gap-2">
        <Input value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} placeholder="Full name" aria-label="Full name" />
        <Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="Title" aria-label="Title" />
        <Input value={f.linkedin_url} onChange={(e) => setF({ ...f, linkedin_url: e.target.value })} placeholder="Profile URL" aria-label="Profile URL" />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Select size="sm" value={f.group} onValueChange={(v) => setF({ ...f, group: v, alumni: v === 'alumni' || f.alumni })} options={ANGLES} aria-label="Who they are" />
        {hiring && <span className="text-xs text-fg-subtle">Saved as hiring team</span>}
        {school && (
          <label className="flex items-center gap-1.5 text-xs text-fg-muted">
            <Checkbox checked={f.alumni} onCheckedChange={(v) => setF({ ...f, alumni: v === true })} />
            {school} alumni
          </label>
        )}
        <Button type="submit" size="sm" variant="default" disabled={f.full_name.trim().length < 2 || add.isPending}>
          Add
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

/** A note or follow-up: Claude drafts it, you edit (autosaved, checked again), copy, send. */
function MessageEditor({ person, kind, appId, max }: { person: LinkedInPerson; kind: 'note' | 'followup'; appId: number; max: number }) {
  const draft = kind === 'note' ? person.note : person.followup
  const run = useDraftLinkedIn(appId)
  const edit = useEditLinkedIn(appId)
  const [text, setText] = useState(draft?.text ?? '')
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const save = (value: string) => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => edit.mutate({ id: person.id, [kind]: value }), 700)
  }
  const limit = draft?.max_chars ?? (kind === 'note' ? max : 600)
  const errors = (draft?.violations ?? []).filter((v) => v.severity === 'error')
  const label = kind === 'note' ? 'Connection note' : 'Follow-up message'
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-fg-subtle">{label}</span>
        {draft && (
          <span className="text-2xs text-fg-subtle">
            {draft.edited ? 'edited · ' : ''}
            {draft.via === 'claude -p' ? `${draft.model} via claude -p${draft.auth === 'none' ? ' · subscription' : ''}` : draft.model} · {relativeTime(draft.created_at)}
          </span>
        )}
        <span className={cn('ml-auto text-2xs tabular-nums', text.length > limit ? 'text-danger-fg' : 'text-fg-subtle')}>
          {text.length} / {limit}
        </span>
      </div>
      {draft ? (
        <Textarea
          value={text}
          onChange={(e) => {
            setText(e.target.value)
            save(e.target.value)
          }}
          className="min-h-16 text-sm"
          aria-label={label}
        />
      ) : (
        <p className="text-xs text-fg-muted">{kind === 'note' ? `Claude drafts a note under ${limit} characters for this person.` : 'One proof from your experience and one direct ask (a referral, or who to talk to).'}</p>
      )}
      {errors.length > 0 && (
        <ul className="space-y-0.5">
          {errors.map((v, i) => (
            <li key={i} className="flex items-start gap-1.5 text-xs text-danger-fg">
              <TriangleAlert className="mt-0.5 size-3 shrink-0" />
              {v.message}
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant={draft ? 'ghost' : 'secondary'}
          disabled={run.isPending}
          onClick={() => run.mutate({ id: person.id, kind }, { onSuccess: () => toast.success(`${label} drafted`), onError: (e) => toast.error(e.message) })}
        >
          <Sparkles />
          {run.isPending ? 'Drafting…' : draft ? 'Redraft' : `Draft ${kind === 'note' ? 'note' : 'follow-up'} with Claude`}
        </Button>
        {draft && (
          <Button size="sm" variant="ghost" onClick={() => navigator.clipboard.writeText(text).then(() => toast.success('Copied: paste it on LinkedIn'))}>
            <Copy />
            Copy
          </Button>
        )}
        {draft && <CritiqueButton kind={kind === 'note' ? 'linkedin_note' : 'linkedin_followup'} id={person.id} />}
        {edit.isPending && <span className="text-2xs text-fg-subtle">Saving…</span>}
      </div>
    </div>
  )
}

function PersonCard({ person, panel }: { person: LinkedInPerson; panel: LinkedInPanel }) {
  const appId = panel.application_id
  const status = useLinkedInStatus(appId)
  const remove = useRemoveLinkedInPerson(appId)
  const add = useAddLinkedInPerson(appId)
  const edit = useEditLinkedIn(appId)
  const st = LINKEDIN_TRACK[person.status]
  const move = (to: LinkedInPerson['status'], message: string) => {
    const from = person.status
    status.mutate(
      { id: person.id, status: to },
      {
        onSuccess: () => toast.success(message, { duration: 8000, action: { label: 'Undo', onClick: () => status.mutate({ id: person.id, status: from }) } }),
        onError: (e) => toast.error(e.message),
      },
    )
  }
  const atLimit = panel.requests_today >= panel.daily_limit
  return (
    <div className="space-y-3 rounded-lg border border-border bg-surface p-3.5" data-tour="linkedin-person">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{person.full_name}</span>
        {person.title && <span className="text-sm text-fg-muted">· {person.title}</span>}
        {person.hiring_team && (
          <ToneBadge tone={GROUP.hiring_team.tone} dot={false}>
            Hiring team
          </ToneBadge>
        )}
        <Tooltip content="Who they are sets the note's angle (detected from the title). Redraft after a change.">
          <span>
            <Select
              size="sm"
              value={person.group === 'hiring_team' ? 'other' : person.group}
              onValueChange={(v) => edit.mutate({ id: person.id, group: v as LinkedInGroup }, { onSuccess: () => toast.success(`${person.full_name}: ${GROUP[v as LinkedInGroup].label}`), onError: (e) => toast.error(e.message) })}
              options={ANGLES.slice(1)}
              aria-label={`Who ${person.full_name} is`}
            />
          </span>
        </Tooltip>
        {person.alumni && person.group !== 'alumni' && <ToneBadge tone="teal">Alumni</ToneBadge>}
        <ToneBadge tone={st.tone}>{st.label}</ToneBadge>
        <span className="ml-auto flex items-center gap-1">
          {person.linkedin_url && (
            <Button size="xs" variant="ghost" asChild>
              <a href={person.linkedin_url} target="_blank" rel="noreferrer">
                Profile
                <ExternalLink />
              </a>
            </Button>
          )}
          {person.status === 'to_contact' && (
            <Tooltip content="Remove (Undo for 8 seconds)">
              <Button
                size="icon-sm"
                variant="ghost"
                aria-label={`Remove ${person.full_name}`}
                onClick={() =>
                  remove.mutate(person.id, {
                    onSuccess: () =>
                      toast(`${person.full_name} removed`, {
                        duration: 8000,
                        action: { label: 'Undo', onClick: () => add.mutate({ full_name: person.full_name, title: person.title, linkedin_url: person.linkedin_url, group: person.group, alumni: person.alumni, hiring_team: person.hiring_team }) },
                      }),
                  })
                }
              >
                <X />
              </Button>
            </Tooltip>
          )}
        </span>
      </div>
      {person.gap_hint && (
        <p className="flex items-center gap-1.5 text-xs text-warning-fg">
          <TriangleAlert className="size-3.5" />
          {person.gap_hint} (a hint: you can still send it)
        </p>
      )}
      {(person.status === 'to_contact' || person.status === 'sent') && (
        <MessageEditor key={`note-${person.note?.created_at}`} person={person} kind="note" appId={appId} max={panel.max_chars} />
      )}
      {(person.status === 'accepted' || person.status === 'messaged' || person.status === 'replied') && (
        <MessageEditor key={`followup-${person.followup?.created_at}`} person={person} kind="followup" appId={appId} max={panel.max_chars} />
      )}
      <div className="flex flex-wrap items-center gap-2 border-t border-border pt-2.5">
        {person.status === 'to_contact' && (
          <Tooltip content={atLimit ? `You've sent ${panel.requests_today} requests today (your limit: ${panel.daily_limit})` : 'After you send it on LinkedIn'}>
            <span>
              <Button size="sm" variant="outline" disabled={!person.note} onClick={() => move('sent', `Request to ${person.full_name} marked sent`)}>
                I sent the request
              </Button>
            </span>
          </Tooltip>
        )}
        {person.status === 'sent' && (
          <Button size="sm" variant="outline" onClick={() => move('accepted', `${person.full_name} accepted: draft the follow-up`)}>
            They accepted
          </Button>
        )}
        {person.status === 'accepted' && (
          <Button size="sm" variant="outline" disabled={!person.followup} onClick={() => move('messaged', `Follow-up to ${person.full_name} marked sent`)}>
            I sent the follow-up
          </Button>
        )}
        {(person.status === 'sent' || person.status === 'messaged') && (
          <Button size="sm" variant="ghost" onClick={() => move('replied', `${person.full_name} replied`)}>
            They replied
          </Button>
        )}
        {person.status !== 'to_contact' && (
          <span className="ml-auto text-2xs text-fg-subtle">
            {person.replied_at
              ? `Replied ${relativeTime(person.replied_at)}`
              : person.messaged_at
                ? `Messaged ${relativeTime(person.messaged_at)}`
                : person.accepted_at
                  ? `Accepted ${relativeTime(person.accepted_at)}`
                  : person.sent_at
                    ? `Request sent ${relativeTime(person.sent_at)}`
                    : ''}
          </span>
        )}
        {person.status !== 'to_contact' && (
          <Tooltip content="Go back one step">
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label="Go back one step"
              onClick={() => {
                const order: LinkedInPerson['status'][] = ['to_contact', 'sent', 'accepted', 'messaged', 'replied']
                move(order[Math.max(0, order.indexOf(person.status) - 1)], 'Moved back one step')
              }}
            >
              <Undo2 />
            </Button>
          </Tooltip>
        )}
      </div>
    </div>
  )
}

/** The LinkedIn messages track for one job: who to message (with search links), the people you
 * add, a note per person, the follow-up after they accept. You send everything yourself. */
export function LinkedInTrackSection({ job }: { job: JobDetail }) {
  const appId = job.application.id
  const { data, isPending, error, refetch } = useLinkedInPanel(appId)
  const [adding, setAdding] = useState<LinkedInGroup | null>(null)
  if (job.application.stage === 'new') return null
  return (
    <Section
      title="LinkedIn messages"
      action={
        <span className="flex items-center gap-3 text-xs text-fg-subtle">
          {data && (
            <span className={cn('tabular-nums', data.requests_today >= data.daily_limit && 'text-warning-fg')}>
              {data.requests_today} / {data.daily_limit} requests today
            </span>
          )}
          <TourButton tour="linkedin-messages" label="How it works" />
        </span>
      }
    >
      <div className="space-y-4 p-4" data-tour="linkedin-track">
        {isPending ? (
          <Skeleton className="h-40" />
        ) : error ? (
          <ErrorState compact error={error} onRetry={() => refetch()} />
        ) : (
          <>
            {data.agency.length > 0 && (
              <p className="flex items-start gap-1.5 rounded-md border border-tone-amber-border bg-warning-bg px-3 py-2 text-xs text-warning-fg">
                <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
                <span>
                  <span className="font-medium">Agency, employer not named</span> ({data.agency.join('; ')}): its alumni and team leads would be the agency's own staff, so message the recruiter first.
                </span>
              </p>
            )}
            <p className="flex flex-wrap items-center gap-1.5 text-xs text-fg-subtle">
              Suggested order:
              {data.order_hint.map((h, i) => (
                <span key={h.step} className={cn(h.done && 'text-success-fg line-through decoration-1')}>
                  {i > 0 && '→ '}
                  {h.step}
                </span>
              ))}
            </p>
            <div className="space-y-2" data-tour="linkedin-groups">
              <p className="text-xs font-medium text-fg-subtle">Who to message, in this order</p>
              {data.groups.map((g) => {
                const count = data.people.filter((p) => (g.group === 'hiring_team' ? p.hiring_team : p.group === g.group && !p.hiring_team)).length
                return (
                  <div key={g.group} className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <ToneBadge tone={GROUP[g.group].tone} dot={false}>
                        {g.label}
                      </ToneBadge>
                      <span className="min-w-0 flex-1 text-xs text-fg-muted">
                        {g.why}
                        {g.group === 'hiring_team' && count === 0 && ' None captured for this job.'}
                      </span>
                      {g.search && (
                        <Button size="xs" variant="ghost" asChild>
                          <a href={g.search} target="_blank" rel="noreferrer">
                            <Search />
                            Search on LinkedIn
                          </a>
                        </Button>
                      )}
                      <Button size="xs" variant="ghost" onClick={() => setAdding(g.group)}>
                        <UserPlus />
                        Add
                      </Button>
                    </div>
                    {adding === g.group && <AddPerson appId={appId} group={g.group} school={data.school} onDone={() => setAdding(null)} />}
                  </div>
                )
              })}
            </div>
            {data.people.length === 0 ? (
              <p className="flex items-center gap-2 text-sm text-fg-muted">
                <ClipboardPaste className="size-4 text-fg-subtle" />
                Nobody added yet: open a search above, pick someone, and add them (paste their profile header).
              </p>
            ) : (
              <div className="space-y-3">
                {data.people.map((p) => (
                  <PersonCard key={p.id} person={p} panel={data} />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </Section>
  )
}
