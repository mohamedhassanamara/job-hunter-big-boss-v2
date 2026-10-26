import { useState } from 'react'
import { toast } from 'sonner'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Select } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { formatDuration, pluralize } from '@/lib/format'
import { useSearchProfile } from '@/lib/queries/library'
import { useRescore, useRescorePreview } from '@/lib/queries/workflow'

const TITLES = {
  all: 'Rescore every job',
  stale: 'Rescore stale jobs',
  outdated: 'Selective & Granular Rescoring',
} as const

export function RescoreModal({
  scope = 'outdated',
  open,
  onOpenChange,
}: {
  scope?: 'all' | 'stale' | 'outdated'
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const profile = useSearchProfile()
  const [track, setTrack] = useState<string>('all')
  const [sinceDays, setSinceDays] = useState<string>('all')
  const [limit, setLimit] = useState<string>('50')
  const [onlyUnscored, setOnlyUnscored] = useState<boolean>(false)

  const preview = useRescorePreview(
    {
      scope,
      track: track === 'all' ? undefined : track,
      since_days: sinceDays === 'all' ? undefined : Number(sinceDays),
      limit: limit === 'all' ? undefined : Number(limit),
      only_unscored: onlyUnscored,
    },
    open,
  )
  const rescore = useRescore()
  const p = preview.data

  const trackOptions = [
    { value: 'all', label: 'All Tracks' },
    ...(profile.data?.tracks ?? []).map((t) => ({
      value: t.name,
      label: t.name,
    })),
  ]

  const dateOptions = [
    { value: 'all', label: 'All time' },
    { value: '7', label: 'Last 7 days' },
    { value: '14', label: 'Last 14 days' },
    { value: '30', label: 'Last 30 days' },
  ]

  const limitOptions = [
    { value: '25', label: '25 jobs' },
    { value: '50', label: '50 jobs' },
    { value: '100', label: '100 jobs' },
    { value: 'all', label: 'No cap (All)' },
  ]

  const isAPInex = p?.model?.startsWith('free/') || p?.model?.includes('minimax') || p?.model === 'apinex'

  const confirm = () => {
    rescore.mutate(
      {
        scope,
        track: track === 'all' ? undefined : track,
        since_days: sinceDays === 'all' ? undefined : Number(sinceDays),
        limit: limit === 'all' ? undefined : Number(limit),
        only_unscored: onlyUnscored,
        confirm: true,
      },
      {
        onSuccess: (r) => {
          toast.success(`${pluralize(r.enqueued, 'job')} queued for rescoring`)
          onOpenChange(false)
        },
        onError: (e) => toast.error(e.message),
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={TITLES[scope]} className="max-w-lg p-0">
        <div className="space-y-4 px-6 py-5">
          <div>
            <h2 className="text-base font-semibold tracking-tight">{TITLES[scope]}</h2>
            <p className="text-xs text-fg-muted">
              Selectively queue jobs by track, recent date window, and batch cap to preserve API quota.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-fg-muted">Track</label>
              <Select
                value={track}
                onValueChange={setTrack}
                options={trackOptions}
                size="sm"
                className="w-full"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-fg-muted">Date Added</label>
              <Select
                value={sinceDays}
                onValueChange={setSinceDays}
                options={dateOptions}
                size="sm"
                className="w-full"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-fg-muted">Batch Cap</label>
              <Select
                value={limit}
                onValueChange={setLimit}
                options={limitOptions}
                size="sm"
                className="w-full"
              />
            </div>

            <div className="flex flex-col justify-end pb-1">
              <label className="flex items-center gap-2 cursor-pointer text-xs font-medium text-fg">
                <Switch checked={onlyUnscored} onCheckedChange={setOnlyUnscored} />
                <span>Only unscored jobs</span>
              </label>
            </div>
          </div>

          <div className="rounded-md border border-border bg-bg-subtle p-3 text-xs">
            {preview.isPending ? (
              <p className="text-fg-muted">Calculating matching jobs…</p>
            ) : preview.error ? (
              <p className="text-danger-fg">{preview.error.message}</p>
            ) : p && p.count === 0 ? (
              <p className="text-fg-muted">No matching jobs found with current filter selections.</p>
            ) : (
              p && (
                <div className="space-y-1">
                  <p className="font-medium text-fg">
                    Queuing {pluralize(p.count, 'matching job')} for scoring with{' '}
                    <span className="font-mono text-2xs text-fg">{p.model}</span>
                    {p.eta_seconds !== null && (
                      <>
                        {' '}
                        (estimated ~
                        {isAPInex
                          ? `${Math.max(1, Math.round(p.eta_seconds / 60))} mins at 15 RPM`
                          : formatDuration(p.eta_seconds)}
                        )
                      </>
                    )}
                    .
                  </p>
                  <p className="text-fg-subtle text-2xs">
                    Current scores are replaced as new scores arrive; labels and stages remain untouched.
                    {p.skipped > 0 && ` ${pluralize(p.skipped, 'job')} skipped as not open or closed.`}
                  </p>
                </div>
              )
            )}
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border px-6 py-3">
          <span className="mr-auto">
            <TourButton tour="rescore" onStart={() => onOpenChange(false)} />
          </span>
          <Button size="sm" variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            size="sm"
            variant="default"
            onClick={confirm}
            disabled={!p || p.count === 0 || rescore.isPending}
          >
            {rescore.isPending ? 'Queuing…' : `Queue ${p && p.count > 0 ? pluralize(p.count, 'job') : ''}`}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
