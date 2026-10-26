import { Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { ErrorState, SkeletonRows } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { useAddDnc, useDncList, useRemoveDnc } from '@/lib/queries/getContact'
import { Card, Field } from './sections'

/** Emails and whole domains nobody may write to. Imports skip them; drafting, approval, LinkedIn notes and the send queue refuse them. */
export function DoNotContactCard() {
  const { data, isPending, error, refetch } = useDncList()
  const add = useAddDnc()
  const remove = useRemoveDnc()
  const [text, setText] = useState('')
  const [reason, setReason] = useState('')

  const onAdd = () =>
    add.mutate(
      { text, reason },
      {
        onSuccess: (r) => {
          setText('')
          setReason('')
          toast.success(r.added ? `${r.added} added to the list` : 'Nothing new to add', {
            description: [
              r.flagged_contacts ? `${r.flagged_contacts} existing contact(s) marked do not contact.` : null,
              r.already_listed ? `${r.already_listed} already listed.` : null,
              r.not_understood.length ? `Not understood: ${r.not_understood.join(', ')}` : null,
            ]
              .filter(Boolean)
              .join(' '),
          })
        },
        onError: (e) => toast.error(e.message),
      },
    )

  return (
    <div data-tour="settings-contacts-dnc">
      <Card
        title="Do not contact"
        description="Paste emails or whole domains (several at once). Imports skip them, and nothing is drafted, approved, put on LinkedIn or sent to them. A contact can also be marked from its card or when you log a reply."
      >
        <div className="space-y-2">
          <Field label="Emails or domains" hint="Separated by spaces, commas or new lines: ana@acme.io, acme.com">
            <Textarea value={text} onChange={(e) => setText(e.target.value)} className="min-h-16" aria-label="Emails or domains" placeholder="ana@acme.io&#10;acme.com" />
          </Field>
          <div className="flex items-center gap-2">
            <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (optional)" aria-label="Reason" className="max-w-sm" />
            <Button size="sm" variant="default" onClick={onAdd} disabled={!text.trim() || add.isPending}>
              Add to the list
            </Button>
          </div>
        </div>
        {isPending ? (
          <SkeletonRows rows={2} />
        ) : error ? (
          <ErrorState error={error} onRetry={() => refetch()} compact />
        ) : data.rules.length === 0 ? (
          <p className="flex flex-wrap items-center gap-2 text-sm text-fg-muted">
            Nobody is listed. Contacts marked from a card or a reply ({data.flagged_contacts}) are protected the same way.
            <TourButton tour="settings" />
          </p>
        ) : (
          <>
            <ul className="divide-y divide-border rounded-lg border border-border bg-surface text-sm">
              {data.rules.map((r) => (
                <li key={r.id} className="flex items-center gap-3 px-3 py-1.5">
                  <span className="w-14 text-xs text-fg-subtle">{r.kind}</span>
                  <span className="min-w-0 flex-1 truncate font-medium">{r.value}</span>
                  <span className="max-w-64 truncate text-xs text-fg-muted">{r.reason}</span>
                  <Button size="icon-sm" variant="ghost" aria-label={`Remove ${r.value}`} onClick={() => remove.mutate(r.id, { onError: (e) => toast.error(e.message) })}>
                    <Trash2 />
                  </Button>
                </li>
              ))}
            </ul>
            <p className="text-xs text-fg-subtle">
              {data.flagged_contacts} contact(s) are marked do not contact. Removing a rule does not lift their mark: open the contact to do that.
            </p>
          </>
        )}
      </Card>
    </div>
  )
}
