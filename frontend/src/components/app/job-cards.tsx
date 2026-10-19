import {
  ChevronDown,
  Copy,
  ExternalLink,
  Mail,
  Search,
  TriangleAlert,
  UserPlus,
  UserRoundX,
} from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useAgencyAction } from '@/hooks/useAgencyAction'
import { relativeTime } from '@/lib/format'
import { useClearJobContact, useCompany, useSetJobContact } from '@/lib/queries/library'
import type { JobDetail, JobListItem, ListingFlag } from '@/lib/types'
import { cn } from '@/lib/utils'
import { ContactAlertBanner } from './ContactAlertBanner'
import { ContactTierBadge, ToneBadge } from './badges'
import { NewContactDialog } from './NewContactDialog'

/** Who this job's email goes to. Change it, add someone, or go back to automatic matching. */
function ChangeContact({ job }: { job: JobDetail }) {
  const company = useCompany(job.company.id)
  const set = useSetJobContact()
  const clear = useClearJobContact()
  const [adding, setAdding] = useState(false)
  const done = (msg: string) => ({ onSuccess: () => toast.success(msg), onError: (e: Error) => toast.error(e.message) })
  // Both routes: after applying you can still pick someone to email, until the email is sent.
  if (job.application.stage === 'closed' || job.application.tracks.outreach === 'sent') return null
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button size="xs" variant="ghost" className="-ml-2">
            Change contact
            <ChevronDown className="text-fg-subtle" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="max-w-80">
          <DropdownMenuLabel>People at {job.company.name}</DropdownMenuLabel>
          {(company.data?.contacts ?? []).map((c) => (
            <DropdownMenuItem
              key={c.id}
              onSelect={() => set.mutate({ appId: job.application.id, contactId: c.id }, done(`Writing to ${c.full_name}`))}
            >
              <span className="min-w-0 flex-1 truncate">
                {c.full_name}
                <span className="text-fg-subtle"> · {c.title ?? 'no title'}</span>
              </span>
            </DropdownMenuItem>
          ))}
          {company.data && company.data.contacts.length === 0 && (
            <DropdownMenuItem disabled>No contacts here yet</DropdownMenuItem>
          )}
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => setAdding(true)}>
            <UserPlus />
            Add a contact…
          </DropdownMenuItem>
          {job.contact && (
            <DropdownMenuItem onSelect={() => clear.mutate(job.application.id, done('Back to automatic matching'))}>
              Automatic (best ranked)
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
      <NewContactDialog
        key={`add-${adding}`}
        open={adding}
        title={`Add a contact at ${job.company.name}`}
        subtitle="Used for this job; matching won't replace your choice."
        submitLabel="Add and use"
        pending={set.isPending}
        onOpenChange={setAdding}
        onSubmit={(contact) =>
          set.mutate(
            { appId: job.application.id, contact },
            { onSuccess: () => { toast.success(`Writing to ${contact.full_name}`); setAdding(false) }, onError: (e) => toast.error(e.message) },
          )
        }
      />
    </>
  )
}

const STATE_BADGE = {
  get: { tone: 'blue', label: 'Get contact' },
  verify: { tone: 'amber', label: 'Verify first' },
  ready: { tone: 'green', label: 'Verified' },
  never: { tone: 'gray', label: 'Never looked up' },
} as const

export function ContactCard({ job, className }: { job: JobDetail; className?: string }) {
  const contact = job.contact
  const open = job.application.stage !== 'new' && job.application.stage !== 'closed'
  const state = STATE_BADGE[job.contact_state]
  const getContact = `/outreach?tab=contacts&app=${job.application.id}`

  const copy = (text: string) => {
    void navigator.clipboard.writeText(text)
    toast.success('Email copied')
  }

  return (
    <div className={cn('rounded-lg border border-border bg-surface p-4', className)}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-fg-subtle">Contact</p>
        {open ? (
          <ToneBadge tone={state.tone} dot={false}>
            {state.label}
          </ToneBadge>
        ) : (
          <ContactTierBadge tier={job.application.contact_tier} />
        )}
      </div>
      {contact ? (
        <div className="space-y-2">
          <div>
            <p className="text-sm font-medium">{contact.full_name}</p>
            <p className="text-sm text-fg-muted">
              {contact.title}
              {contact.role_label && contact.role_label !== contact.title && <span className="text-fg-subtle"> · {contact.role_label}</span>}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-1">
            {contact.email && (
              <Button size="xs" variant="ghost" onClick={() => copy(contact.email!)} className="-ml-2">
                <Mail />
                {contact.email}
                <Copy className="text-fg-subtle" />
              </Button>
            )}
            {contact.linkedin_url && (
              <Button size="xs" variant="ghost" asChild>
                <a href={contact.linkedin_url} target="_blank" rel="noreferrer">
                  LinkedIn
                  <ExternalLink />
                </a>
              </Button>
            )}
          </div>
          {open && job.contact_state === 'verify' && (
            <p className="text-xs text-warning-fg">
              Not verified yet: the email waits until you check they're still there.{' '}
              <Link to={getContact} className="text-primary hover:underline">
                Verify now
              </Link>
            </p>
          )}
          <ContactAlertBanner
            alerts={job.contact_alerts}
            nextContact={job.next_contact}
            appId={job.application.id}
            contactId={contact.id}
            contactName={contact.full_name}
            companyName={job.company.name}
            className="text-xs"
          />
          <ChangeContact job={job} />
          <p className="text-xs text-fg-subtle">
            {job.company_contacts > 1 ? `${job.company_contacts - 1} more at ${job.company.name} · ` : ''}
            <Link to={`/contacts?company=${job.company.id}`} className="text-primary hover:underline">
              View company contacts
            </Link>
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex gap-2.5 text-sm">
            <UserRoundX className="mt-0.5 size-4 shrink-0 text-fg-subtle" />
            <div>
              <p>
                {job.contact_search === 'never'
                  ? `${job.company.name} is never looked up (a job board).`
                  : job.contact_search === 'not_found'
                    ? 'You found nobody there with the Apollo extension.'
                    : `Nobody at ${job.company.name} yet.`}
              </p>
              <p className="text-fg-muted">
                {job.contact_search === 'never'
                  ? 'This job goes to web apply.'
                  : open
                    ? 'Find someone with the Apollo extension in the Get contact step.'
                    : 'Shortlist the job to find someone in the Get contact step.'}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {open && job.contact_search !== 'never' && (
              <Button size="sm" asChild>
                <Link to={getContact}>
                  <Search />
                  Get contact
                </Link>
              </Button>
            )}
            <ChangeContact job={job} />
          </div>
        </div>
      )}
    </div>
  )
}

/** Duplicate / already-contacted callouts. */
export function JobFlags({ job, compact }: { job: JobListItem & { agency?: string[]; listing_flags?: ListingFlag[] }; compact?: boolean }) {
  const flags: { key: string; text: React.ReactNode; action?: React.ReactNode }[] = []
  const agency = useAgencyAction()
  if (job.agency?.length) {
    flags.push({
      key: 'agency',
      text: (
        <>
          <span className="font-medium">Agency, employer not named</span> ({job.agency.join('; ')}). Contacts and LinkedIn messages go to the recruiter first.
        </>
      ),
      action: (
        <Button size="xs" variant="ghost" className="-my-1 shrink-0" disabled={agency.pending} onClick={() => agency.run(job.company, job.company.agency_override === 'agency' ? null : 'employer')}>
          {job.company.agency_override === 'agency' ? 'Let the rule decide' : "It's an employer"}
        </Button>
      ),
    })
  }
  if (job.duplicate_of_id) {
    flags.push({
      key: 'dup',
      text: (
        <>
          Duplicate of a listing from another source.{' '}
          <Link to={`/jobs/${job.duplicate_of_id}`} className="font-medium underline-offset-2 hover:underline">
            Open original
          </Link>
        </>
      ),
    })
  }
  if (job.company_contacted) {
    flags.push({
      key: 'contacted',
      text: (
        <>
          You already contacted or applied to {job.company.name}
          {job.company.contacted_at ? ` (${relativeTime(job.company.contacted_at)})` : ''}.
        </>
      ),
    })
  }
  for (const f of job.listing_flags ?? []) flags.push({ key: `listing-${f.kind}`, text: f.text })
  if (!flags.length) return null
  return (
    <div className={cn('space-y-1.5', compact && 'text-xs')}>
      {flags.map((f) => (
        <div
          key={f.key}
          data-tour={f.key.startsWith('listing-') ? 'listing-flags' : undefined}
          className="flex gap-2 rounded-md border border-tone-amber-border bg-warning-bg px-3 py-2 text-sm text-warning-fg"
        >
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
          <span className="min-w-0 flex-1">{f.text}</span>
          {f.action}
        </div>
      ))}
    </div>
  )
}

export function ExternalListingButton({ url, label = 'Open listing' }: { url: string; label?: string }) {
  return (
    <Button size="sm" variant="ghost" asChild>
      <a href={url} target="_blank" rel="noreferrer">
        {label}
        <ExternalLink />
      </a>
    </Button>
  )
}

/** The company card's answer to the agency rule: mark it an agency, or undo your answer. */
export function AgencyLine({ job }: { job: JobDetail }) {
  const agency = useAgencyAction()
  const answer = job.company.agency_override
  if (!answer && job.agency.length > 0) return null // the flag above offers "It's an employer"
  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-2 text-xs text-fg-subtle">
      {answer && <span>You marked it as {answer === 'agency' ? 'a recruiting agency' : 'an employer'}.</span>}
      <Button size="xs" variant="ghost" className="-mx-2" disabled={agency.pending} onClick={() => agency.run(job.company, answer ? null : 'agency')}>
        {answer ? 'Let the rule decide' : "It's a recruiting agency"}
      </Button>
    </div>
  )
}
