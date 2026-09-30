import { CircleCheck, LoaderCircle } from 'lucide-react'
import type { DraftProgress } from '@/lib/types'
import { cn } from '@/lib/utils'

const PHASES = [
  { key: 'fetching', label: 'Fetching pages' },
  { key: 'extracting', label: 'Extracting signals' },
  { key: 'drafting', label: 'Drafting' },
] as const

/** The draft step's phases while it runs (research first, reused when fresh). */
export function DraftProgressLine({ state }: { state: DraftProgress | undefined }) {
  const phase = state?.phase ?? 'starting'
  const current = PHASES.findIndex((p) => p.key === phase)
  return (
    <ol className="flex flex-wrap items-center gap-3 text-sm" aria-live="polite" data-tour="draft-progress">
      {PHASES.map((p, i) => {
        const done = current > i || phase === 'done'
        const active = current === i
        return (
          <li key={p.key} className={cn('flex items-center gap-1.5', active ? 'font-medium text-fg' : done ? 'text-fg-muted' : 'text-fg-subtle')}>
            {done ? <CircleCheck className="size-4 text-success-dot" /> : active ? <LoaderCircle className="size-4 animate-spin text-primary" /> : <span className="size-4 rounded-full border border-border-strong" />}
            {p.label}
            {active && state && state.total > 0 && ` (${state.done}/${state.total})`}
          </li>
        )
      })}
    </ol>
  )
}
