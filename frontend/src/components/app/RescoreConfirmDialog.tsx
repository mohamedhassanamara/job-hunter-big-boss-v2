import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { formatDuration, pluralize } from '@/lib/format'
import { useRescore, useRescorePreview } from '@/lib/queries/workflow'

const TITLES = { all: 'Rescore every job', stale: 'Rescore stale jobs', outdated: 'Rescore outdated jobs' } as const

/** Rescoring jobs that already have a valid score is always explicit: this dialog shows how
 * many jobs, which model and roughly how long before anything is queued. */
export function RescoreConfirmDialog({
  scope,
  open,
  onOpenChange,
}: {
  scope: 'all' | 'stale' | 'outdated'
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const preview = useRescorePreview(scope, open)
  const rescore = useRescore()
  const p = preview.data
  const confirm = () =>
    rescore.mutate(
      { scope, confirm: true },
      {
        onSuccess: (r) => {
          toast.success(`${pluralize(r.enqueued, 'job')} queued for rescoring`)
          onOpenChange(false)
        },
        onError: (e) => toast.error(e.message),
      },
    )
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={TITLES[scope]} className="max-w-md p-0">
        <div className="space-y-1 px-5 py-4">
          <h2 className="text-md font-semibold tracking-tight">{TITLES[scope]}?</h2>
          {preview.isPending ? (
            <p className="text-sm text-fg-muted">Counting…</p>
          ) : preview.error ? (
            <p className="text-sm text-danger-fg">{preview.error.message}</p>
          ) : p && p.count === 0 ? (
            <p className="text-sm text-fg-muted">Nothing to rescore.</p>
          ) : (
            p && (
              <p className="text-sm text-fg-muted">
                {pluralize(p.count, 'job')} will be scored again with <span className="font-mono text-xs text-fg">{p.model}</span>,{' '}
                {p.days
                  ? `in about ${p.days} ${p.days === 1 ? 'day' : 'days'} of free quota (${p.daily_capacity}/day, best jobs first, it carries on by itself)`
                  : formatDuration(p.eta_seconds)}
                . Their current scores are replaced when the new ones arrive; labels and stages don't change.
                {p.skipped > 0 && ` ${pluralize(p.skipped, 'job')} skipped as not open (closed, duplicate, filtered or expired).`}
              </p>
            )
          )}
        </div>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
          <Button size="sm" variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button size="sm" variant="default" onClick={confirm} disabled={!p || p.count === 0 || rescore.isPending}>
            Rescore {p ? pluralize(p.count, 'job') : ''}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
