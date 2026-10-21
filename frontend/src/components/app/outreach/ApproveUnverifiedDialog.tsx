import { CircleX, ShieldOff, TriangleAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import type { Draft } from '@/lib/types'
import { cn } from '@/lib/utils'

/** "Approve without verification": this draft only. Lists everything still outstanding, then approves. */
export function ApproveUnverifiedDialog({
  draft,
  open,
  onClose,
  pending,
  onConfirm,
}: {
  draft: Draft
  open: boolean
  onClose: () => void
  pending: boolean
  onConfirm: () => void
}) {
  const issues = [
    ...draft.violations.map((v) => ({ severity: v.severity, message: v.message })),
    ...(draft.verification_state === 'passed'
      ? []
      : [{ severity: 'warning' as const, message: `The claim verifier is skipped${draft.verification_state === 'none' ? '' : ` (its last result: ${draft.verification_state})`}` }]),
    ...draft.contact_alerts.map((a) => ({ severity: 'warning' as const, message: `${draft.contact?.full_name ?? 'The contact'} may have left (${a.reason})` })),
  ]
  const errors = issues.filter((i) => i.severity === 'error').length
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Approve without verification" className="max-w-lg p-0">
        <div className="space-y-3 px-5 py-4">
          <div>
            <h2 className="text-md font-semibold tracking-tight">Approve without verification</h2>
            <p className="text-sm text-fg-muted">
              This draft only: the Claude claim verifier and the blocking checks are skipped. It is marked “approved without verification” with today’s date and the list below. Before it is sent, the
              exact text, the attached CV, the contact and the CV version must still be what you approve now.
            </p>
          </div>
          {issues.length === 0 ? (
            <p className="text-sm text-fg-muted">Nothing is outstanding.</p>
          ) : (
            <ul className="max-h-64 space-y-1 overflow-y-auto rounded-md border border-border bg-surface px-3 py-2">
              {issues.map((i, n) => (
                <li key={n} className={cn('flex items-start gap-2 text-sm', i.severity === 'error' ? 'text-danger-fg' : 'text-warning-fg')}>
                  {i.severity === 'error' ? <CircleX className="mt-0.5 size-4 shrink-0" /> : <TriangleAlert className="mt-0.5 size-4 shrink-0" />}
                  <span>{i.message}</span>
                </li>
              ))}
            </ul>
          )}
          {errors > 0 && <p className="text-xs text-danger-fg">{errors} blocking problem{errors === 1 ? '' : 's'} will be ignored: an unchecked fact may reach the recipient.</p>}
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-3">
          <Button size="sm" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" variant="danger" disabled={pending} onClick={onConfirm}>
            <ShieldOff />
            {pending ? 'Approving…' : 'Approve without verification'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

/** The mark an unverified approval carries (visible in the draft, the queue and the job). */
export function UnverifiedBadge({ at, ignored }: { at?: string; ignored?: number }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-sm bg-warning-bg px-1.5 py-0.5 text-xs font-medium text-warning-fg">
      <ShieldOff className="size-3" />
      Approved without verification
      {at && <span className="font-normal"> · {new Date(at).toLocaleDateString()}</span>}
      {ignored ? <span className="font-normal"> · {ignored} ignored</span> : null}
    </span>
  )
}
