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
import { relativeTime } from '@/lib/format'
import { useQueueLookup } from '@/lib/queries/jobs'
import { useClearJobContact, useCompany, useSetJobContact } from '@/lib/queries/library'
import type { JobDetail, JobListItem } from '@/lib/types'
import { cn } from '@/lib/utils'
import { ContactAlertBanner } from './ContactAlertBanner'
import { ContactTierBadge } from './badges'
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

export function ContactCard({ job, className }: { job: JobDetail; className?: string }) {
  const lookup = useQueueLookup()
  const tier = job.application.contact_tier
  const contact = job.contact

  const copy = (text: string) => {
    void navigator.clipboard.writeText(text)
    toast.success('Email copied')
  }

  return (
    <div className={cn('rounded-lg border border-border bg-surface p-4', className)}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-fg-subtle">Contact</p>
        <ContactTierBadge tier={tier} />
      </div>
      {contact ? (
        <div className="space-y-2">
          <div>
            <p className="text-sm font-medium">{contact.full_name}</p>
            <p className="text-sm text-fg-muted">
              {contact.title}
              {contact.role_label && <span className="text-fg-subtle"> · {contact.role_label}</span>}
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
      ) : tier === 'lookup_queued' ? (
        <div className="space-y-2">
          <div className="flex gap-2.5 text-sm">
            <Search className="mt-0.5 size-4 shrink-0 text-warning-dot" />
            <div>
              <p>{job.company.name} is in the Apollo lookup queue.</p>
              <p className="text-fg-muted">
                Lookups are capped daily.{' '}
                <Link to="/contacts?tab=lookups" className="text-primary hover:underline">
                  Open the queue
                </Link>
              </p>
            </div>
          </div>
          <ChangeContact job={job} />
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex gap-2.5 text-sm">
            <UserRoundX className="mt-0.5 size-4 shrink-0 text-fg-subtle" />
            <div>
              <p>{job.lookup_status === 'not_found' ? 'The Apollo lookup found nobody.' : 'No contact at this company.'}</p>
              <p className="text-fg-muted">This job goes to web apply unless you add someone.</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              onClick={() =>
                lookup.mutate(job.application.id, {
                  onSuccess: () => toast.success('Queued for an Apollo lookup'),
                  onError: (e) => toast.error(e.message),
                })
              }
              disabled={lookup.isPending}
            >
              <Search />
              {job.lookup_status === 'not_found' ? 'Look up again' : 'Queue Apollo lookup'}
            </Button>
            <ChangeContact job={job} />
          </div>
        </div>
      )}
    </div>
  )
}

/** Duplicate / already-contacted callouts. */
export function JobFlags({ job, compact }: { job: JobListItem; compact?: boolean }) {
  const flags: { key: string; text: React.ReactNode }[] = []
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
  if (!flags.length) return null
  return (
    <div className={cn('space-y-1.5', compact && 'text-xs')}>
      {flags.map((f) => (
        <div
          key={f.key}
          className="flex gap-2 rounded-md border border-tone-amber-border bg-warning-bg px-3 py-2 text-sm text-warning-fg"
        >
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
          <span>{f.text}</span>
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
