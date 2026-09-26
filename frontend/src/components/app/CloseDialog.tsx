import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import type { CloseReason } from '@/lib/types'
import { cn } from '@/lib/utils'

const REASONS: { value: CloseReason; label: string; hint: string }[] = [
  { value: 'rejected', label: 'Rejected', hint: 'The company said no' },
  { value: 'no_response', label: 'No response', hint: 'Went quiet after outreach' },
  { value: 'withdrawn', label: 'Withdrew', hint: 'I decided not to continue' },
  { value: 'offer', label: 'Got an offer', hint: 'Closing on a high note' },
  { value: 'dismissed', label: 'Not a fit', hint: 'Dismiss without contacting' },
]

/** Asks why an application is being closed. Used by Pipeline drag and the Job stage menu. */
export function CloseDialog({
  open,
  title,
  onCancel,
  onConfirm,
}: {
  open: boolean
  title: string
  onCancel: () => void
  onConfirm: (reason: CloseReason) => void
}) {
  const [reason, setReason] = useState<CloseReason>('rejected')
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent title="Close application" className="max-w-md p-0">
        <div className="border-b border-border px-5 py-4">
          <h2 className="text-md font-semibold tracking-tight">Close application</h2>
          <p className="truncate text-sm text-fg-muted">{title}</p>
        </div>
        <div className="space-y-1 p-3" role="radiogroup" aria-label="Reason">
          {REASONS.map((r) => (
            <button
              key={r.value}
              role="radio"
              aria-checked={reason === r.value}
              onClick={() => setReason(r.value)}
              onDoubleClick={() => onConfirm(r.value)}
              className={cn(
                'flex w-full items-center gap-3 rounded-md px-3 py-2 text-left transition-colors duration-120',
                reason === r.value ? 'bg-surface-selected' : 'hover:bg-surface-hover',
              )}
            >
              <span
                className={cn(
                  'flex size-4 items-center justify-center rounded-full border',
                  reason === r.value ? 'border-primary' : 'border-border-strong',
                )}
              >
                {reason === r.value && <span className="size-2 rounded-full bg-primary" />}
              </span>
              <span className="flex-1">
                <span className="block text-sm font-medium">{r.label}</span>
                <span className="block text-xs text-fg-muted">{r.hint}</span>
              </span>
            </button>
          ))}
        </div>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
          <Button size="sm" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
          <Button size="sm" variant="default" onClick={() => onConfirm(reason)}>
            Close application
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
