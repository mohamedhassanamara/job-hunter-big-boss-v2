import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { AFTER_APPLY_REASONS, BEFORE_APPLY_REASONS, CLOSE_REASON_LABELS } from '@/lib/tracking'
import type { CloseReason } from '@/lib/types'
import { cn } from '@/lib/utils'

const HINTS: Partial<Record<CloseReason, string>> = {
  rejected: 'The company said no',
  no_response: 'No reply after applying (ghosted)',
  withdrawn: 'I decided not to continue',
  offer_accepted: 'Closing on a high note',
  offer_declined: 'Got an offer and said no',
  dismissed: 'Dismiss without applying',
}

/** Asks why an application is being closed. After applying the reasons are real outcomes
 * (rejected, no response, withdrew, offer accepted/declined); before, dismissed or withdrew. */
export function CloseDialog({
  open,
  title,
  applied = false,
  initial,
  onCancel,
  onConfirm,
}: {
  open: boolean
  title: string
  applied?: boolean
  initial?: CloseReason
  onCancel: () => void
  onConfirm: (reason: CloseReason) => void
}) {
  const options = applied ? AFTER_APPLY_REASONS : BEFORE_APPLY_REASONS
  const REASONS = options.map((value) => ({ value, label: CLOSE_REASON_LABELS[value], hint: HINTS[value] ?? '' }))
  const [reason, setReason] = useState<CloseReason>(initial && options.includes(initial) ? initial : options[0])
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
