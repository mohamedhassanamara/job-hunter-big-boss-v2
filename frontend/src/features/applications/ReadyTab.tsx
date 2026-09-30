import { ArrowUpRight, CircleCheck, FileText, Globe } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { EmptyState, ErrorState, SkeletonRows } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { MarkAppliedDialog } from '@/components/app/tracking/TrackingDialogs'
import { Button } from '@/components/ui/button'
import { Kbd } from '@/components/ui/kbd'
import { useListKeyboard } from '@/hooks/useListKeyboard'
import { apiUrl } from '@/lib/api'
import { countryName } from '@/lib/format'
import { useReadyToApply } from '@/lib/queries/tracking'
import { openListingAndCv } from '@/lib/tracking'
import type { ReadyItem } from '@/lib/types'
import { cn } from '@/lib/utils'

const pdfUrl = (r: ReadyItem) => apiUrl(`/cv/${r.cv_version_id}/pdf`, { download: true })
const letterUrl = (r: ReadyItem) => (r.letter_status === 'approved' && r.letter_id ? apiUrl(`/letters/${r.letter_id}/pdf`, { download: true }) : null)

export function ReadyTab() {
  const { data, isPending, error, refetch } = useReadyToApply()
  const [selected, setSelected] = useState<number | null>(null)
  const [applying, setApplying] = useState<ReadyItem | null>(null)
  const items = data ?? []
  const byId = (id: number) => items.find((r) => r.application_id === id)

  useListKeyboard({
    ids: items.map((r) => r.application_id),
    selectedId: selected,
    onSelect: setSelected,
    actions: {
      o: (id) => {
        const r = byId(id)
        if (r) openListingAndCv(r.url, pdfUrl(r), letterUrl(r))
      },
      a: (id) => setApplying(byId(id) ?? null),
    },
    enabled: !applying,
  })

  if (isPending) return <SkeletonRows rows={5} />
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />
  if (items.length === 0)
    return (
      <EmptyState
        icon={Globe}
        title="Nothing ready to apply"
        description="Jobs land here when their CV is approved and there's no contact to email. Approve a CV in CV Studio to start."
        action={
          <div className="flex gap-2">
            <Button asChild size="sm" variant="default">
              <Link to="/pipeline">Open Pipeline</Link>
            </Button>
            <TourButton tour="applications" />
          </div>
        }
      />
    )

  return (
    <div className="min-h-0 flex-1 overflow-y-auto" data-tour="applications-ready">
      <p className="border-b border-border bg-bg-subtle px-6 py-2 text-xs text-fg-subtle">
        <Kbd>O</Kbd> open listing + download CV (and cover letter) · <Kbd>A</Kbd> mark applied · <Kbd>J</Kbd> <Kbd>K</Kbd> move
      </p>
      <div role="listbox" aria-label="Ready to apply">
        {items.map((r) => (
          <div
            key={r.application_id}
            data-row-id={r.application_id}
            role="option"
            aria-selected={selected === r.application_id}
            onClick={() => setSelected(r.application_id)}
            className={cn(
              'relative flex cursor-default items-center gap-3 border-b border-border px-6 py-3 transition-colors duration-120',
              selected === r.application_id ? 'bg-surface-selected' : 'hover:bg-surface-hover',
            )}
          >
            {selected === r.application_id && <span className="absolute inset-y-0 left-0 w-0.5 bg-primary" />}
            <div className="min-w-0 flex-1">
              <Link to={`/jobs/${r.job_id}`} className="truncate text-sm font-medium hover:underline">
                {r.title}
              </Link>
              <p className="truncate text-xs text-fg-muted">
                {r.company} · {r.track ?? 'No track'} · {r.country ? countryName(r.country) : 'Remote'} · approved CV v{r.cv_version}
                {r.letter_status === 'approved' && ` · cover letter v${r.letter_version}`}
              </p>
            </div>
            {r.letter_status !== 'approved' && (
              <Button size="sm" variant="ghost" asChild data-tour="applications-letter">
                <Link to={`/jobs/${r.job_id}/letter`}>
                  <FileText />
                  {r.letter_status === 'draft' ? `Review cover letter v${r.letter_version}` : 'Write cover letter'}
                </Link>
              </Button>
            )}
            <Button
              size="sm"
              variant={(selected ?? items[0].application_id) === r.application_id ? 'default' : 'secondary'}
              data-tour="applications-open" onClick={() => openListingAndCv(r.url, pdfUrl(r), letterUrl(r))}>
              {r.letter_status === 'approved' ? 'Open listing + CV + cover letter' : 'Open listing + CV'}
              <ArrowUpRight />
            </Button>
            <Button size="sm" data-tour="applications-mark" onClick={() => setApplying(r)}>
              <CircleCheck />
              Mark applied
            </Button>
          </div>
        ))}
      </div>
      <MarkAppliedDialog
        key={applying?.application_id ?? 'none'}
        target={applying ? { appId: applying.application_id, title: applying.title, company: applying.company } : null}
        cvVersion={applying?.cv_version ?? null}
        cvVersionId={applying?.cv_version_id}
        onOpenChange={(o) => !o && setApplying(null)}
      />
    </div>
  )
}
