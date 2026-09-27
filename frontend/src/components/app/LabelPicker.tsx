import { Kbd } from '@/components/ui/kbd'
import { Tooltip } from '@/components/ui/tooltip'
import type { UserLabel } from '@/lib/types'
import { cn } from '@/lib/utils'

const OPTIONS: { value: UserLabel; label: string; key: string; on: string }[] = [
  { value: 'good', label: 'Good', key: '1', on: 'bg-tone-green-bg text-tone-green-fg border-tone-green-border' },
  { value: 'maybe', label: 'Maybe', key: '2', on: 'bg-tone-amber-bg text-tone-amber-fg border-tone-amber-border' },
  { value: 'no', label: 'No', key: '3', on: 'bg-tone-gray-bg text-tone-gray-fg border-tone-gray-border' },
]

/** Your judgment of a job (Good / Maybe / No) — used to evaluate the scorer, not a stage. */
export function LabelPicker({
  value,
  onChange,
  compact = false,
}: {
  value: UserLabel | null
  onChange: (label: UserLabel | null) => void
  compact?: boolean
}) {
  return (
    <div role="radiogroup" aria-label="Your label" className="inline-flex items-center gap-1">
      {OPTIONS.map((o) => {
        const active = value === o.value
        return (
          <Tooltip
            key={o.value}
            content={
              <span className="flex items-center gap-1.5">
                {active ? 'Remove label' : `Label ${o.label}`} <Kbd>{o.key}</Kbd>
              </span>
            }
          >
            <button
              role="radio"
              aria-checked={active}
              onClick={(e) => {
                e.stopPropagation()
                onChange(active ? null : o.value)
              }}
              className={cn(
                'inline-flex items-center gap-1 rounded-md border font-medium transition-colors duration-120',
                compact ? 'h-6 px-1.5 text-2xs' : 'h-7 px-2 text-xs',
                active ? o.on : 'border-border bg-surface text-fg-muted hover:bg-surface-hover hover:text-fg',
              )}
            >
              {o.label}
              {!compact && <span className="text-2xs text-fg-subtle tabular-nums">{o.key}</span>}
            </button>
          </Tooltip>
        )
      })}
    </div>
  )
}
