import { ChevronDown, Search, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Kbd } from '@/components/ui/kbd'
import { Select } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { countryName, REMOTE_LABELS, SOURCE_LABELS } from '@/lib/format'
import { useSearchProfile } from '@/lib/queries/library'
import type { JobFilters } from '@/lib/queries/jobs'
import { cn } from '@/lib/utils'
import { hasActiveFilters } from './filters'

const SOURCE_OPTIONS = Object.entries(SOURCE_LABELS).map(([value, label]) => ({ value, label }))
const REMOTE_OPTIONS = (['remote', 'hybrid', 'onsite'] as const).map((value) => ({
  value,
  label: REMOTE_LABELS[value],
}))
const SCORE_OPTIONS = [
  { value: 'any', label: 'Any fit' },
  { value: '50', label: 'Fit 50+' },
  { value: '65', label: 'Fit 65+' },
  { value: '80', label: 'Fit 80+' },
]
const POSTED_OPTIONS = [
  { value: 'any', label: 'Any time' },
  { value: '1', label: 'Last 24 hours' },
  { value: '3', label: 'Last 3 days' },
  { value: '7', label: 'Last 7 days' },
  { value: '14', label: 'Last 14 days' },
]

function MultiFilter({
  label,
  options,
  selected,
  onChange,
}: {
  label: string
  options: { value: string; label: string }[]
  selected: string[]
  onChange: (values: string[]) => void
}) {
  const active = selected.length > 0
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          size="sm"
          variant="secondary"
          className={cn(active && 'border-primary/40 bg-primary-subtle text-fg')}
        >
          {label}
          {active && (
            <span className="rounded-sm bg-primary px-1 text-2xs font-semibold text-primary-fg tabular-nums">
              {selected.length}
            </span>
          )}
          <ChevronDown className="size-3.5! text-fg-subtle" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        <DropdownMenuLabel>{label}</DropdownMenuLabel>
        {options.map((o) => (
          <DropdownMenuCheckboxItem
            key={o.value}
            checked={selected.includes(o.value)}
            onSelect={(e) => e.preventDefault()}
            onCheckedChange={(checked) =>
              onChange(checked ? [...selected, o.value] : selected.filter((v) => v !== o.value))
            }
          >
            {o.label}
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function FilterBar({
  filters,
  onChange,
  onClear,
  hideScores = false,
}: {
  filters: JobFilters
  onChange: (patch: Partial<JobFilters>) => void
  onClear: () => void
  /** Blind labeling: fit-based filters would reveal scores, so they are off. */
  hideScores?: boolean
}) {
  const profile = useSearchProfile()
  // Target countries from Settings, plus jobs with no country (usually remote).
  const countryOptions = [...(profile.data?.locations ?? []), 'REMOTE'].map((value) => ({ value, label: countryName(value) }))
  return (
    <div data-tour="discover-filters" className="flex flex-wrap items-center gap-2 border-b border-border bg-bg px-6 py-2.5">
      <div className="relative w-64">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-fg-subtle" />
        <Input
          data-page-search
          value={filters.q ?? ''}
          onChange={(e) => onChange({ q: e.target.value })}
          onKeyDown={(e) => e.key === 'Escape' && e.currentTarget.blur()}
          placeholder="Filter by title or company"
          className="h-7 pr-8 pl-8"
        />
        <Kbd className="absolute top-1/2 right-2 -translate-y-1/2">/</Kbd>
      </div>
      <MultiFilter
        label="Source"
        options={SOURCE_OPTIONS}
        selected={filters.source ?? []}
        onChange={(source) => onChange({ source })}
      />
      <MultiFilter
        label="Remote"
        options={REMOTE_OPTIONS}
        selected={filters.remote ?? []}
        onChange={(remote) => onChange({ remote })}
      />
      <MultiFilter
        label="Country"
        options={countryOptions}
        selected={filters.country ?? []}
        onChange={(country) => onChange({ country })}
      />
      <Select
        size="sm"
        aria-label="Minimum fit"
        value={filters.min_score ? String(filters.min_score) : 'any'}
        onValueChange={(v) => onChange({ min_score: v === 'any' ? null : Number(v) })}
        options={SCORE_OPTIONS}
        disabled={hideScores}
      />
      <Select
        size="sm"
        aria-label="Posted within"
        value={filters.posted_within ? String(filters.posted_within) : 'any'}
        onValueChange={(v) => onChange({ posted_within: v === 'any' ? null : Number(v) })}
        options={POSTED_OPTIONS}
      />
      <Select
        size="sm"
        aria-label="Red flags"
        value={filters.flags ?? 'any'}
        onValueChange={(v) => onChange({ flags: v === 'any' ? null : (v as JobFilters['flags']) })}
        options={[
          { value: 'any', label: 'Any flags' },
          { value: 'hide_hard', label: 'Hide disqualifying' },
          { value: 'only_flagged', label: 'Only flagged' },
        ]}
        disabled={hideScores}
      />
      <Select
        size="sm"
        aria-label="Your label"
        value={filters.label ?? 'any'}
        onValueChange={(v) => onChange({ label: v === 'any' ? null : (v as JobFilters['label']) })}
        options={[
          { value: 'any', label: 'Any label' },
          { value: 'unlabeled', label: 'Unlabeled' },
          { value: 'good', label: 'Labeled Good' },
          { value: 'maybe', label: 'Labeled Maybe' },
          { value: 'no', label: 'Labeled No' },
        ]}
      />
      <label className="flex h-7 items-center gap-2 px-1 text-sm text-fg-muted">
        <Switch
          checked={!!filters.hide_duplicates}
          onCheckedChange={(hide_duplicates) => onChange({ hide_duplicates })}
        />
        Hide duplicates
      </label>
      <div className="ml-auto flex items-center gap-2">
        {hasActiveFilters(filters) && (
          <Button size="sm" variant="ghost" onClick={onClear}>
            <X />
            Clear filters
          </Button>
        )}
      </div>
    </div>
  )
}
