import { Building2, ChevronDown, CircleCheck, ExternalLink, Globe, Pencil, Search, Undo2, UserRoundCheck, UserRoundX, Users } from 'lucide-react'
import { useRef, useState } from 'react'
import { toast } from 'sonner'
import { ContactAlertBanner } from '@/components/app/ContactAlertBanner'
import { ContactForm } from '@/components/app/contact/ContactForm'
import { FindContactCard } from '@/components/app/contact/FindContactCard'
import { ErrorState } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Kbd } from '@/components/ui/kbd'
import { Skeleton } from '@/components/ui/skeleton'
import { useHotkeys } from '@/hooks/useHotkeys'
import { relativeTime } from '@/lib/format'
import { useContactSearch, useEditContact, useFoundContact, useGetContact, useNotAggregator, useVerifyContact } from '@/lib/queries/getContact'
import { useSetJobContact } from '@/lib/queries/library'
import type { GetContactView } from '@/lib/types'
import { cn } from '@/lib/utils'

const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '')

function LinkButton({ href, icon: Icon, children }: { href: string | null; icon: typeof Globe; children: React.ReactNode }) {
  if (!href) return null
  return (
    <Button size="sm" variant="outline" asChild>
      <a href={href} target="_blank" rel="noreferrer">
        <Icon />
        {children}
        <ExternalLink className="text-fg-subtle" />
      </a>
    </Button>
  )
}

function Where({ v }: { v: GetContactView }) {
  const p = v.provenance
  if (!p) return null
  const from = p.kind === 'import' ? `From ${p.label}, imported ${day(p.at)}` : `Entered by ${p.label}, ${day(p.at)}`
  const checked = v.verified_at
    ? `${v.stale ? 'Last verified' : 'Verified'} ${relativeTime(v.verified_at)}${v.stale ? ` (over ${v.verify_days} days: check again)` : ''}`
    : 'Never verified'
  return (
    <p className="text-xs text-fg-subtle">
      {from} · <span className={cn(v.stale || !v.verified_at ? 'text-warning-fg' : 'text-fg-subtle')}>{checked}</span>
    </p>
  )
}

/** Verify first: a contact exists (e.g. from a CSV) but you haven't confirmed they're there. */
function VerifyFirst({ v, hotkeys, onDone }: { v: GetContactView; hotkeys: boolean; onDone?: () => void }) {
  const verify = useVerifyContact()
  const edit = useEditContact()
  const [editing, setEditing] = useState(false)
  const [menu, setMenu] = useState(false)
  const c = v.contact!
  const act = (action: 'still_there' | 'left' | 'wrong_person') =>
    verify.mutate(
      { appId: v.application_id, action },
      {
        onSuccess: (next) => {
          if (action === 'still_there') toast.success(`${c.full_name} verified`, { description: 'Ready to draft the email.' })
          else toast(`${c.full_name} won't be picked again`, { description: next?.contact ? `Next by your ranking: ${next.contact.full_name}` : 'Find a replacement below.' })
          if (action === 'still_there') onDone?.()
        },
        onError: (e) => toast.error(e.message),
      },
    )
  useHotkeys({ v: () => c.email && act('still_there'), l: () => setMenu(true), e: () => setEditing(true) }, { enabled: hotkeys && !editing && !verify.isPending })

  return (
    <div className="space-y-3" data-tour="verify-first">
      <div className="flex items-start gap-3 rounded-lg border border-border bg-surface px-3.5 py-3">
        <div className="min-w-0 flex-1 space-y-1">
          <p className="text-sm font-medium">
            {c.full_name}
            {c.title && <span className="font-normal text-fg-muted"> · {c.title}</span>}
          </p>
          <p className="text-xs text-fg-muted">{c.email ?? <span className="text-warning-fg">No email yet: add it with Edit details</span>}</p>
          <Where v={v} />
        </div>
        <LinkButton href={v.links.profile} icon={Users}>
          {c.linkedin_url ? 'Their LinkedIn' : 'Find on LinkedIn'}
        </LinkButton>
      </div>
      {v.alerts.length > 0 && (
        <ContactAlertBanner alerts={v.alerts} nextContact={null} appId={v.application_id} contactId={c.id} contactName={c.full_name} companyName={v.company.name} actions={false} />
      )}
      <p className="text-xs text-fg-muted">Open their profile: are they still at {v.company.name}, in this role? Then choose.</p>
      {editing ? (
        <ContactForm
          appId={v.application_id}
          companyName={v.company.name}
          initial={{ full_name: c.full_name, title: c.title ?? '', email: c.email ?? '', linkedin_url: c.linkedin_url ?? '' }}
          submitLabel="Save details"
          pending={edit.isPending}
          withPaste={false}
          onCancel={() => setEditing(false)}
          onSubmit={(fields) =>
            edit.mutate(
              { appId: v.application_id, contactId: c.id, fields },
              { onSuccess: () => (setEditing(false), toast.success('Details saved')), onError: (e) => toast.error(e.message) },
            )
          }
        />
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="default" onClick={() => act('still_there')} disabled={!c.email || verify.isPending}>
            <UserRoundCheck />
            Still there, verified
            {hotkeys && <Kbd className="border-transparent bg-primary-hover text-primary-fg">V</Kbd>}
          </Button>
          <DropdownMenu open={menu} onOpenChange={setMenu}>
            <DropdownMenuTrigger asChild>
              <Button size="sm" variant="outline" disabled={verify.isPending}>
                <UserRoundX />
                Left or wrong person
                {hotkeys && <Kbd>L</Kbd>}
                <ChevronDown className="text-fg-subtle" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <DropdownMenuItem onSelect={() => act('left')}>Left the company: find a replacement</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => act('wrong_person')}>Wrong person: find someone else</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
            <Pencil />
            Edit details
            {hotkeys && <Kbd>E</Kbd>}
          </Button>
        </div>
      )}
    </div>
  )
}

/** Who to look for: roles for this company, links, steps, the entry form (with paste). */
function WhoToLookFor({ v, hotkeys, onDone }: { v: GetContactView; hotkeys: boolean; onDone?: () => void }) {
  const found = useFoundContact()
  const search = useContactSearch()
  const notBoard = useNotAggregator()
  const pick = useSetJobContact()
  const pasteRef = useRef<HTMLTextAreaElement>(null)
  const nobody = v.company.contact_search === 'not_found'
  const mark = (status: 'not_found' | 'never') =>
    search.mutate(
      { companyId: v.company.id, status, appId: v.application_id },
      {
        onSuccess: () => {
          toast(status === 'never' ? `${v.company.name}: never looked up` : `Nobody found at ${v.company.name}`, {
            description: status === 'never' ? 'Its jobs go to web apply.' : 'Try Hunter, or apply on the web.',
            duration: 8000,
            action: { label: 'Undo', onClick: () => search.mutate({ companyId: v.company.id, status: 'none', appId: v.application_id }) },
          })
          onDone?.()
        },
        onError: (e) => toast.error(e.message),
      },
    )
  useHotkeys({ p: () => pasteRef.current?.focus(), n: () => !nobody && mark('not_found'), x: () => mark('never') }, { enabled: hotkeys && !found.isPending })

  return (
    <div className="space-y-4" data-tour="who-to-look-for">
      {nobody && (
        <p className="flex items-center gap-2 rounded-md bg-warning-bg px-3 py-2 text-xs text-warning-fg">
          You found nobody at {v.company.name} with the extension{v.company.contact_search_notes ? ` (${v.company.contact_search_notes})` : ''}. Try Hunter, or apply on the web.
          <Button size="xs" variant="ghost" className="ml-auto" onClick={() => search.mutate({ companyId: v.company.id, status: 'none', appId: v.application_id })}>
            <Undo2 />
            Look again
          </Button>
        </p>
      )}
      {v.company.aggregator.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-md bg-warning-bg px-3 py-2 text-xs text-warning-fg">
          Looks like a job board: {v.company.aggregator.join(', ')}.
          <span className="ml-auto flex gap-1">
            <Button size="xs" variant="ghost" onClick={() => mark('never')}>
              Never look up
            </Button>
            <Button size="xs" variant="ghost" onClick={() => notBoard.mutate({ companyId: v.company.id, appId: v.application_id })}>
              It's an employer
            </Button>
          </span>
        </div>
      )}
      <FindContactCard key={`find-${v.application_id}`} appId={v.application_id} domain={v.company.domain} onUsed={onDone} />
      <div className="space-y-2 border-t border-border pt-3">
        <p className="text-xs font-medium text-fg-subtle">Or by hand, with the Apollo extension</p>
        <p className="text-sm">{v.who.reason}</p>
        <ol className="space-y-1 text-sm">
          {v.who.roles.map((r, i) => (
            <li key={r.label} className="flex flex-wrap items-baseline gap-x-2">
              <span className="w-4 text-xs text-fg-subtle tabular-nums">{i + 1}.</span>
              <span className="font-medium">{r.label}</span>
              <span className="text-xs text-fg-subtle">{r.titles.join(' · ')}</span>
            </li>
          ))}
        </ol>
      </div>
      <div className="flex flex-wrap gap-2" data-tour="get-contact-links">
        <LinkButton href={v.links.people_search} icon={Search}>
          LinkedIn: these roles at {v.company.name}
        </LinkButton>
        <LinkButton href={v.links.company_linkedin} icon={Building2}>
          Company on LinkedIn
        </LinkButton>
        <LinkButton href={v.links.website} icon={Globe}>
          Website
        </LinkButton>
      </div>
      <ol className="list-decimal space-y-0.5 pl-5 text-xs text-fg-muted">
        {v.who.steps.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ol>
      {v.others.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-fg-subtle">Already known at {v.company.name}</p>
          <div className="flex flex-wrap gap-2">
            {v.others.map((o) => (
              <Button
                key={o.id}
                size="sm"
                variant="outline"
                className="h-auto min-h-7 py-1 text-left whitespace-normal"
                disabled={pick.isPending}
                onClick={() =>
                  pick.mutate({ appId: v.application_id, contactId: o.id }, { onSuccess: () => toast.success(`Writing to ${o.full_name}: verify them next`), onError: (e) => toast.error(e.message) })
                }
              >
                {o.full_name}
                {o.title && <span className="font-normal text-fg-subtle">· {o.title}</span>}
              </Button>
            ))}
          </div>
        </div>
      )}
      <ContactForm
        key={v.application_id}
        appId={v.application_id}
        companyName={v.company.name}
        submitLabel="Save contact"
        quiet
        pending={found.isPending}
        pasteRef={pasteRef}
        onSubmit={(fields, via) =>
          found.mutate(
            { appId: v.application_id, fields, via },
            {
              onSuccess: () => {
                toast.success(`${fields.full_name} saved and verified`, { description: 'Ready to draft the email.' })
                onDone?.()
              },
              onError: (e) => toast.error(e.message),
            },
          )
        }
      />
      <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
        {!nobody && (
          <Button size="sm" variant="ghost" onClick={() => mark('not_found')} disabled={search.isPending}>
            Nobody found
            {hotkeys && <Kbd>N</Kbd>}
          </Button>
        )}
        <Button size="sm" variant="ghost" onClick={() => mark('never')} disabled={search.isPending}>
          Never look up (a job board)
          {hotkeys && <Kbd>X</Kbd>}
        </Button>
        {hotkeys && (
          <span className="ml-auto text-2xs text-fg-subtle">
            <Kbd>P</Kbd> paste box
          </span>
        )}
      </div>
    </div>
  )
}

/** The Get contact step for one job: "Verify first" when a contact exists, "Who to look for"
 * when not. Drafting (and research) stay blocked until the contact is verified. */
export function GetContactPanel({ appId, hotkeys = false, onDone, className }: { appId: number; hotkeys?: boolean; onDone?: () => void; className?: string }) {
  const { data, isPending, error, refetch } = useGetContact(appId)
  const search = useContactSearch()
  if (isPending) return <Skeleton className={cn('h-48', className)} />
  if (error) return <ErrorState error={error} onRetry={() => refetch()} compact />
  const v = data
  return (
    <div className={className} data-tour="get-contact">
      {v.state === 'verify' && v.contact ? (
        <VerifyFirst v={v} hotkeys={hotkeys} onDone={onDone} />
      ) : v.state === 'get' ? (
        <WhoToLookFor v={v} hotkeys={hotkeys} onDone={onDone} />
      ) : v.state === 'never' ? (
        <div className="flex flex-wrap items-center gap-2 text-sm text-fg-muted">
          {v.company.name} is never looked up (a job board or aggregator): apply on the web.
          <Button size="xs" variant="ghost" onClick={() => search.mutate({ companyId: v.company.id, status: 'none', appId })}>
            <Undo2 />
            Look it up after all
          </Button>
        </div>
      ) : (
        <p className="flex items-center gap-2 text-sm">
          <CircleCheck className="size-4 text-success-fg" />
          {v.contact?.full_name} verified {relativeTime(v.verified_at!)}: ready to draft.
        </p>
      )}
    </div>
  )
}
