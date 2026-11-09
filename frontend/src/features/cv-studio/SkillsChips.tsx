import { CircleCheck, TriangleAlert, Undo2, X } from 'lucide-react'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip } from '@/components/ui/tooltip'
import { useCVSkills } from '@/lib/queries/workflow'
import type { CVPatchInput, CVSkillsFit, SkillChip } from '@/lib/types'
import { cn } from '@/lib/utils'
import { fitSummary } from './skillsFit'

/** The skills line of a job CV as chips: take a skill off, put one back from your own skills
 * (never free text). The CV prints exactly your list once you edit it; the page is re-fitted and
 * the line rule (2-3 lines, last line at least 75% full, at least the minimum) is only reported. */
export function SkillsChips({
  cvId,
  readOnly,
  busy,
  onPatch,
}: {
  cvId: number
  readOnly: boolean
  busy: boolean
  onPatch: (patch: CVPatchInput) => void
}) {
  const { data, isPending, error, refetch } = useCVSkills(cvId)
  if (isPending) return <Skeleton className="h-16" />
  if (error || !data) {
    return (
      <p className="text-xs text-danger-fg">
        Could not load the skills line.{' '}
        <button className="underline" onClick={() => void refetch()}>
          Retry
        </button>
      </p>
    )
  }
  if (data.mode === 'grouped') {
    return (
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-md border border-dashed border-border-strong px-3 py-3 text-xs text-fg-muted">
        <span className="min-w-0 flex-1">
          This CV prints your skill groups: the listing names none of your skills, so there is no listing-ordered line to edit.
        </span>
        <TourButton tour="cv" />
      </div>
    )
  }
  const locked = readOnly || busy
  const options = data.available.map((c) => ({ value: c.skill, label: optionLabel(c) }))
  return (
    <div className="space-y-2">
      <FitLine fit={data.fit} />
      {data.printed.length === 0 ? (
        <p className="rounded-md border border-dashed border-border-strong px-3 py-3 text-xs text-fg-muted">
          No automatic skills line fits the 2-3 line rule for this listing, so your skill groups print. Add skills below to build the line yourself.
        </p>
      ) : (
        <ul className="flex flex-wrap gap-1.5" aria-label="Skills on this CV">
          {data.printed.map((c) => (
            <li key={c.skill}>
              <Chip chip={c} disabled={locked} onRemove={() => onPatch({ skills: { remove: [c.skill] } })} />
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Select
          size="sm"
          className="w-56"
          value={undefined}
          placeholder={options.length ? 'Add one of your skills…' : 'Nothing left to add'}
          aria-label="Add one of your skills"
          disabled={locked || options.length === 0}
          options={options}
          onValueChange={(skill) => onPatch({ skills: { add: [skill] } })}
        />
        {data.fit.manual && (
          <Button size="xs" variant="ghost" disabled={locked} onClick={() => onPatch({ skills: { reset: true } })}>
            <Undo2 />
            Back to automatic
          </Button>
        )}
        <TourButton tour="cv" label="How the line is chosen" />
      </div>
      {readOnly && <p className="text-2xs text-fg-subtle">This version is read only.</p>}
    </div>
  )
}

function optionLabel(c: SkillChip) {
  return c.kind === 'soft' ? `${c.skill} (soft skill)` : c.tier === 3 ? `${c.skill} (certification)` : c.tier === 2 ? `${c.skill} (small project)` : c.skill
}

function Chip({ chip, disabled, onRemove }: { chip: SkillChip; disabled: boolean; onRemove: () => void }) {
  return (
    <Tooltip content={chip.source}>
      <span
        className={cn(
          'inline-flex h-6 items-center gap-1 rounded-full border border-border bg-surface pr-0.5 pl-2.5 text-xs',
          chip.kind === 'soft' && 'border-dashed',
        )}
      >
        {chip.skill}
        <button
          type="button"
          disabled={disabled}
          onClick={onRemove}
          aria-label={`Remove ${chip.skill}`}
          className="rounded-full p-0.5 text-fg-subtle hover:bg-surface-hover hover:text-fg disabled:opacity-40"
        >
          <X className="size-3" />
        </button>
      </span>
    </Tooltip>
  )
}

/** "17 skills · 2 lines · last line 78%", and what breaks the rule when something does. */
function FitLine({ fit }: { fit: CVSkillsFit }) {
  const ok = fit.ok
  return (
    <div className={cn('rounded-md px-2.5 py-1.5 text-xs', ok ? 'bg-bg-subtle text-fg-muted' : 'bg-warning-bg text-warning-fg')} aria-live="polite">
      <p className="flex items-center gap-1.5">
        {ok ? <CircleCheck className="size-3.5 text-success-dot" /> : <TriangleAlert className="size-3.5" />}
        <span className="tabular-nums">{fitSummary(fit)}</span>
        {fit.manual && <span className="text-fg-subtle">· your list</span>}
      </p>
      {!ok && (
        <ul className="mt-1 list-disc space-y-0.5 pl-5">
          {fit.problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
