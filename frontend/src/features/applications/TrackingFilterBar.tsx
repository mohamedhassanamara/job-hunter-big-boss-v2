import { Download, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { MultiFilter } from '@/features/discover/FilterBar'
import { countryName, SOURCE_LABELS } from '@/lib/format'
import { useSearchProfile } from '@/lib/queries/library'
import { exportCsvUrl, useTracked } from '@/lib/queries/tracking'
import type { Source } from '@/lib/types'
import { useTrackingFilters } from './filters'

const STAGE_OPTIONS = [
  { value: 'done', label: 'Applied / sent' },
  { value: 'interview', label: 'Interview' },
  { value: 'closed', label: 'Closed' },
]

/** Track, country, source, stage and date range, all in the URL; shared by Applied and Stats. */
export function TrackingFilterBar({ showExport = false }: { showExport?: boolean }) {
  const { filters, active, set, clear } = useTrackingFilters()
  const profile = useSearchProfile()
  const everything = useTracked({})
  const rows = everything.data ?? []
  const tracks = [...new Set([...(profile.data?.tracks ?? []).map((t) => t.name), ...rows.map((r) => r.track ?? '')])].filter(Boolean)
  const countries = [...new Set(rows.map((r) => r.country ?? 'REMOTE'))]
  const sources = [...new Set(rows.map((r) => r.source))]

  return (
    <div data-tour="applications-filters" className="flex flex-wrap items-center gap-2 border-b border-border bg-bg px-6 py-2.5">
      <MultiFilter
        label="Track"
        options={[...tracks.map((t) => ({ value: t, label: t })), { value: 'NONE', label: 'No track' }]}
        selected={filters.track ?? []}
        onChange={(v) => set({ track: v })}
      />
      <MultiFilter
        label="Country"
        options={countries.map((c) => ({ value: c, label: c === 'REMOTE' ? 'Remote / none' : countryName(c) }))}
        selected={filters.country ?? []}
        onChange={(v) => set({ country: v })}
      />
      <MultiFilter
        label="Source"
        options={sources.map((s) => ({ value: s, label: SOURCE_LABELS[s as Source] ?? s }))}
        selected={filters.source ?? []}
        onChange={(v) => set({ source: v })}
      />
      <MultiFilter label="Stage" options={STAGE_OPTIONS} selected={filters.stage ?? []} onChange={(v) => set({ stage: v })} />
      <div className="flex items-center gap-1.5 text-xs text-fg-muted">
        Applied
        <Input
          type="date"
          aria-label="Applied from"
          value={filters.start ?? ''}
          onChange={(e) => set({ from: e.target.value || null })}
          className="h-7 w-36"
        />
        to
        <Input
          type="date"
          aria-label="Applied to"
          value={filters.end ?? ''}
          onChange={(e) => set({ to: e.target.value || null })}
          className="h-7 w-36"
        />
      </div>
      {active && (
        <Button size="sm" variant="ghost" onClick={clear}>
          <X />
          Clear
        </Button>
      )}
      {showExport && (
        <Button size="sm" variant="ghost" asChild className="ml-auto" data-tour="applications-export">
          <a href={exportCsvUrl(filters)} download>
            <Download />
            Export CSV
          </a>
        </Button>
      )}
    </div>
  )
}
