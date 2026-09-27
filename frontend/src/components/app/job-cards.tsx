import {
  Copy,
  ExternalLink,
  Mail,
  Search,
  TriangleAlert,
  UserRoundX,
} from 'lucide-react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { relativeTime } from '@/lib/format'
import { useQueueLookup } from '@/lib/queries/jobs'
import type { JobDetail, JobListItem } from '@/lib/types'
import { cn } from '@/lib/utils'
import { ContactTierBadge } from './badges'

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
            <p className="text-sm text-fg-muted">{contact.title}</p>
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
          <p className="text-xs text-fg-subtle">
            {job.company_contacts > 1 ? `${job.company_contacts - 1} more at ${job.company.name} · ` : ''}
            <Link to={`/contacts?company=${job.company.id}`} className="text-primary hover:underline">
              View company contacts
            </Link>
          </p>
        </div>
      ) : tier === 'lookup_queued' ? (
        <div className="flex gap-2.5 text-sm">
          <Search className="mt-0.5 size-4 shrink-0 text-warning-dot" />
          <div>
            <p>Waiting for a manual Apollo lookup.</p>
            <p className="text-fg-muted">Lookups are capped daily. See the queue in Contacts.</p>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex gap-2.5 text-sm">
            <UserRoundX className="mt-0.5 size-4 shrink-0 text-fg-subtle" />
            <div>
              <p>No contact in your Apollo import.</p>
              <p className="text-fg-muted">Queue a lookup, or apply on the web instead.</p>
            </div>
          </div>
          <Button
            size="sm"
            onClick={() =>
              lookup.mutate(job.application.id, {
                onSuccess: () => toast.success('Queued for Apollo lookup'),
                onError: (e) => toast.error(e.message),
              })
            }
            disabled={lookup.isPending}
          >
            <Search />
            Queue Apollo lookup
          </Button>
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
