import { ExternalLink, RefreshCw, TriangleAlert, UserRoundCheck } from 'lucide-react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { useCheckContact, useDismissContactAlert, useSetJobContact } from '@/lib/queries/library'
import type { Contact, ContactAlert } from '@/lib/types'
import { cn } from '@/lib/utils'

const host = (url: string) => url.replace(/^https?:\/\/(www\.)?/, '').split('/')[0]
const when = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : null)

/** "Contact may have left": what research found, the next contact by your ranking, and
 * "I've verified them" (undo toast). While it shows, the email can't be approved. */
export function ContactAlertBanner({
  alerts,
  nextContact,
  appId,
  contactId,
  contactName,
  companyName,
  jobId,
  className,
}: {
  alerts: ContactAlert[]
  nextContact: Contact | null
  appId: number
  contactId: number
  contactName: string
  companyName: string
  /** Set outside the job page: links there to change the contact. */
  jobId?: number
  className?: string
}) {
  const dismiss = useDismissContactAlert()
  const check = useCheckContact()
  const setContact = useSetJobContact()
  if (!alerts.length) return null
  const [first, ...rest] = alerts

  const verified = () => {
    const ids = alerts.map((a) => a.id)
    Promise.all(ids.map((id) => dismiss.mutateAsync({ id, dismissed: true })))
      .then(() =>
        toast.success(`Kept ${contactName} as the contact`, {
          description: 'The warning is dismissed; the email can be approved.',
          duration: 8000,
          action: { label: 'Undo', onClick: () => ids.forEach((id) => dismiss.mutate({ id, dismissed: false })) },
        }),
      )
      .catch((e: Error) => toast.error(e.message))
  }
  const again = () =>
    check.mutate(contactId, {
      onSuccess: (r) =>
        r.alerts.length
          ? toast.error(`Still flagged: ${r.alerts[0].reason}`, { description: `${r.pages} pages and news items checked` })
          : toast.success(`Nothing suggests ${contactName} left`, { description: `${r.pages} pages and news items checked` }),
      onError: (e) => toast.error(e.message),
    })
  const switchTo = (c: Contact) =>
    setContact.mutate(
      { appId, contactId: c.id },
      { onSuccess: () => toast.success(`Writing to ${c.full_name}`, { description: 'Regenerate the email for them.' }), onError: (e) => toast.error(e.message) },
    )

  return (
    <div role="alert" data-tour="contact-alert" className={cn('space-y-2.5 rounded-lg border border-tone-red-border bg-danger-bg px-3.5 py-3 text-sm', className)}>
      <p className="flex items-center gap-2 font-medium text-danger-fg">
        <TriangleAlert className="size-4 shrink-0" />
        {contactName} may have left {companyName}
      </p>
      <div className="space-y-1 text-fg">
        <p className="text-fg-muted">
          {first.kind === 'new_holder' ? `Research found that ${first.reason}` : `Research found ${first.reason}`}
          {rest.length ? ` (and ${rest.length} more sign${rest.length === 1 ? '' : 's'})` : ''}:
        </p>
        <blockquote className="border-l-2 border-tone-red-border pl-2.5 text-fg">“{first.excerpt}”</blockquote>
        <p className="flex min-w-0 items-center gap-1.5 text-xs text-fg-subtle">
          {first.source_url ? (
            <a href={first.source_url} target="_blank" rel="noreferrer" title={first.source_title || first.source_url} className="flex min-w-0 items-center gap-1 text-primary hover:underline">
              <span className="truncate">{first.source_title || host(first.source_url)}</span>
              <ExternalLink className="size-3 shrink-0" />
            </a>
          ) : (
            <span className="truncate">{first.source_title}</span>
          )}
          {when(first.page_date) && <span className="shrink-0">· {when(first.page_date)}</span>}
        </p>
      </div>
      <p className="text-xs text-fg-muted">The email can't be approved until you write to someone else, or confirm {contactName} is still there.</p>
      {!nextContact && (
        <p className="text-xs text-fg-muted">
          No other contact at {companyName} with an email yet:{' '}
          {jobId ? (
            <Link to={`/jobs/${jobId}`} className="text-primary hover:underline">
              add one on the job page
            </Link>
          ) : (
            'add one with Change contact below'
          )}
          .
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {nextContact && (
          <Button size="sm" variant="outline" onClick={() => switchTo(nextContact)} disabled={setContact.isPending} className="h-auto min-h-8 py-1.5 text-left whitespace-normal">
            Write to {nextContact.full_name} instead
            {nextContact.title && <span className="font-normal text-fg-subtle">· {nextContact.title}</span>}
          </Button>
        )}
        <Button size="sm" variant="ghost" onClick={verified} disabled={dismiss.isPending}>
          <UserRoundCheck />
          I've verified them
        </Button>
        <Button size="sm" variant="ghost" onClick={again} disabled={check.isPending}>
          <RefreshCw className={check.isPending ? 'animate-spin' : undefined} />
          {check.isPending ? 'Checking…' : 'Check again'}
        </Button>
      </div>
    </div>
  )
}
