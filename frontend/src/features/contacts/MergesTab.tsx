import { GitMerge } from 'lucide-react'
import { toast } from 'sonner'
import { EmptyState, ErrorState, SkeletonRows } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { pluralize } from '@/lib/format'
import { useMergeAction, useMergeSuggestions } from '@/lib/queries/library'
import type { MergeSide, MergeSuggestion } from '@/lib/types'

const side = (s: MergeSide) => `${pluralize(s.jobs, 'job')} · ${pluralize(s.contacts, 'contact')}`

/** Suggested duplicates ("Devoteam Belgium" vs "Devoteam"), confirmed one by one. Never automatic. */
export function MergesTab() {
  const { data, isPending, error, refetch } = useMergeSuggestions()
  const act = useMergeAction()
  const keep = (kept: MergeSide, gone: MergeSide) =>
    act.mutate(
      { keep_id: kept.id, merge_id: gone.id },
      {
        onSuccess: () => toast.success(`Merged into ${kept.name}`, { description: `“${gone.name}” now maps to ${kept.name}; jobs re-matched.` }),
        onError: (e) => toast.error(e.message),
      },
    )
  const reject = (m: MergeSuggestion) =>
    act.mutate(
      { a_id: m.a.id, b_id: m.b.id },
      { onSuccess: () => toast.success('Kept apart', { description: `${m.a.name} and ${m.b.name} won't be suggested again.` }), onError: (e) => toast.error(e.message) },
    )

  if (isPending) return <SkeletonRows rows={6} className="mx-6 my-5" />
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />
  return (
    <div className="mx-auto max-w-5xl space-y-4 px-6 py-6" data-tour="contacts-merges">
      <p className="text-sm text-fg-muted">
        Possible duplicates: one name is the other plus a country, legal form or group word, or both share a website. Nothing
        is merged until you confirm. Merging moves jobs, contacts and the Get contact state to the name you keep, and future jobs under the
        other spelling land there too. The database is backed up before the first merge.
      </p>
      <div className="rounded-lg border border-border bg-surface">
        {data.length === 0 ? (
          <EmptyState compact icon={GitMerge} title="No suggested merges" description="New suggestions appear as jobs and imports add companies." />
        ) : (
          data.map((m) => (
            <div key={`${m.a.id}-${m.b.id}`} className="flex items-center gap-4 border-b border-border px-4 py-3 last:border-b-0">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm">
                  <span className="font-medium">{m.a.name}</span> <span className="text-fg-subtle">({side(m.a)})</span>
                  <span className="px-2 text-fg-subtle">and</span>
                  <span className="font-medium">{m.b.name}</span> <span className="text-fg-subtle">({side(m.b)})</span>
                </p>
                <p className="truncate text-xs text-fg-muted">{m.reason}</p>
              </div>
              <Button size="sm" variant="ghost" onClick={() => reject(m)} disabled={act.isPending}>
                Different companies
              </Button>
              <Button size="sm" onClick={() => keep(m.b, m.a)} disabled={act.isPending}>
                Keep “{m.b.name}”
              </Button>
              <Button size="sm" onClick={() => keep(m.a, m.b)} disabled={act.isPending}>
                Keep “{m.a.name}”
              </Button>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
