import { CircleCheck, LoaderCircle, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { ToneBadge } from '@/components/app/badges'
import { EmptyState, ErrorState } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { useHeaderPreview, useRefreshHeaders } from '@/lib/queries/workflow'
import type { HeaderResult } from '@/lib/types'

const pct = (fill: number | null) => (fill == null ? '' : ` · ${Math.round(fill * 100)}% full`)

/** "Refresh headers": lists the unsent CVs (drafts and approved) whose header differs from the current
 * Candidate profile and links, then re-renders only that header, locally. Sent CVs are never listed. */
export function RefreshHeadersDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const preview = useHeaderPreview(open)
  const refresh = useRefreshHeaders()
  const [results, setResults] = useState<HeaderResult[] | null>(null)
  const rows = preview.data ?? []
  const done = results ?? []
  const fixed = done.filter((r) => r.outcome === 'refreshed').length
  const close = () => {
    setResults(null)
    onClose()
  }
  return (
    <Dialog open={open} onOpenChange={(o) => !o && close()}>
      <DialogContent title="Refresh headers" className="max-w-2xl p-0">
        <div className="space-y-3 px-5 py-4">
          <div>
            <h2 className="text-md font-semibold tracking-tight">Refresh headers</h2>
            <p className="text-sm text-fg-muted">
              Re-renders each CV&apos;s header (name, contact line, links) from Settings → Candidate. Bullets, skills, summary and layout are not touched, nothing is regenerated, approved CVs stay
              approved and sent CVs are never changed.
            </p>
          </div>
          {preview.error ? (
            <ErrorState error={preview.error} onRetry={() => void preview.refetch()} />
          ) : preview.isPending ? (
            <p className="text-sm text-fg-muted">Checking your CVs…</p>
          ) : results ? (
            <div className="space-y-2">
              <p className="text-sm font-medium" data-testid="header-report">
                {fixed} of {done.length} refreshed
              </p>
              <ul className="max-h-72 divide-y divide-border overflow-y-auto rounded-md border border-border text-xs">
                {done.map((r) => (
                  <li key={r.id} className="flex items-center gap-2 px-3 py-1.5">
                    <span className="flex-1 truncate">
                      CV #{r.id} v{r.version}
                    </span>
                    <span className="tabular-nums text-fg-muted">
                      {r.pages_after ?? r.pages_before} page{(r.pages_after ?? r.pages_before) === 1 ? '' : 's'}
                      {pct(r.fill_after ?? r.fill_before)}
                    </span>
                    <ToneBadge tone={r.outcome === 'refreshed' || r.outcome === 'unchanged' ? 'green' : 'red'}>{r.outcome === 'not_saved' ? 'not saved' : r.outcome}</ToneBadge>
                    {r.reason && <span className="max-w-48 truncate text-fg-subtle">{r.reason}</span>}
                  </li>
                ))}
              </ul>
            </div>
          ) : rows.length === 0 ? (
            <EmptyState icon={CircleCheck} title="Every header is up to date" description="Nothing to change: the unsent CVs already show your current name, contact line and links." />
          ) : (
            <div className="space-y-2">
              <p className="text-sm font-medium" data-testid="header-list-count">
                {rows.length} CV{rows.length === 1 ? '' : 's'} will change
              </p>
              <ul className="max-h-72 divide-y divide-border overflow-y-auto rounded-md border border-border text-xs">
                {rows.map((r) => (
                  <li key={r.id} className="flex items-center gap-2 px-3 py-1.5">
                    <span className="flex-1 truncate">
                      {r.company} · {r.title}
                    </span>
                    <span className="tabular-nums text-fg-muted">
                      v{r.version}
                      {r.pages != null && ` · ${r.pages} page${r.pages === 1 ? '' : 's'}`}
                      {pct(r.fill)}
                    </span>
                    <ToneBadge tone={r.status === 'approved' ? 'green' : 'gray'}>{r.status}</ToneBadge>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-3">
          <Button size="sm" variant="ghost" onClick={close}>
            {results ? 'Close' : 'Cancel'}
          </Button>
          {!results && (
            <Button size="sm" variant="default" disabled={refresh.isPending || rows.length === 0} onClick={() => refresh.mutate(null, { onSuccess: setResults })}>
              {refresh.isPending ? <LoaderCircle className="animate-spin" /> : <RefreshCw />}
              Refresh {rows.length} header{rows.length === 1 ? '' : 's'}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
