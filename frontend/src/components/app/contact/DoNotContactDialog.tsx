import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { useSetContactDnc } from '@/lib/queries/getContact'
import type { Contact } from '@/lib/types'

/** Mark a contact "asked not to be contacted". Their jobs move to the next contact; Undo lifts it. */
export function DoNotContactDialog({ contact, open, onOpenChange }: { contact: Contact; open: boolean; onOpenChange: (open: boolean) => void }) {
  const [reason, setReason] = useState('')
  const set = useSetContactDnc()
  const submit = () =>
    set.mutate(
      { contactId: contact.id, flag: true, reason: reason.trim() || undefined },
      {
        onSuccess: () => {
          onOpenChange(false)
          setReason('')
          toast(`${contact.full_name} is marked do not contact`, {
            description: 'No email, LinkedIn note or send for them. Their jobs move to the next contact.',
            duration: 8000,
            action: { label: 'Undo', onClick: () => set.mutate({ contactId: contact.id, flag: false }) },
          })
        },
        onError: (e) => toast.error(e.message),
      },
    )
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Asked not to be contacted" className="max-w-md p-0">
        <div className="border-b border-border px-5 py-4">
          <h2 className="text-md font-semibold tracking-tight">Asked not to be contacted</h2>
          <p className="truncate text-sm text-fg-muted">{contact.full_name}</p>
        </div>
        <div className="space-y-2 px-5 py-4">
          <p className="text-sm text-fg-muted">Nothing is drafted, approved, queued or sent for them, and imports never touch them again. Only you can lift it.</p>
          <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (optional): replied, asked by phone…" aria-label="Reason" onKeyDown={(e) => e.key === 'Enter' && submit()} />
        </div>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
          <Button size="sm" variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button size="sm" variant="default" onClick={submit} disabled={set.isPending}>
            Mark do not contact
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
