import { ChevronDown, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { ErrorState, SkeletonRows } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'
import { usePendingDelete } from '@/hooks/usePendingDelete'
import { absoluteDate } from '@/lib/format'
import { useDeleteWoop, useSaveWoop, useWoops } from '@/lib/queries/motivation'
import type { Woop } from '@/lib/types'
import { cn } from '@/lib/utils'

type Field = 'wish' | 'outcome' | 'obstacle' | 'plan'
const FIELDS: { key: Field; letter: string; label: string; help: string; placeholder: string }[] = [
  { key: 'wish', letter: 'W', label: 'Wish', help: 'Something you want that is challenging but within reach in the next weeks.', placeholder: 'e.g. Get two interviews for data engineering roles this month' },
  { key: 'outcome', letter: 'O', label: 'Outcome', help: 'The best result of reaching it. Picture it for a moment: how would it feel?', placeholder: 'e.g. Talking about my lakehouse project with a team I want to join' },
  { key: 'obstacle', letter: 'O', label: 'Obstacle', help: 'The main thing inside you that gets in the way (a habit, a feeling, a thought).', placeholder: 'e.g. After a rejection I stop sending for days' },
  { key: 'plan', letter: 'P', label: 'Plan', help: 'If the obstacle shows up, then what will you do? One concrete if-then sentence.', placeholder: 'If a rejection arrives, then I open the Start tab and do one tiny task right away.' },
]
const EMPTY: Record<Field, string> = { wish: '', outcome: '', obstacle: '', plan: '' }

function SavedWoop({ woop, onDelete }: { woop: Woop; onDelete: () => void }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-lg border border-border bg-surface">
      <button className="flex w-full items-center gap-3 px-4 py-3 text-left" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">{woop.wish}</span>
          <span className="text-xs text-fg-subtle">{absoluteDate(woop.created_at)}</span>
        </span>
        <ChevronDown className={cn('size-4 text-fg-subtle transition-transform duration-120', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="space-y-3 border-t border-border px-4 py-3">
          {FIELDS.map((f) => (
            <div key={f.key}>
              <p className="text-xs font-medium text-fg-subtle">{f.label}</p>
              <p className="text-sm whitespace-pre-wrap">{woop[f.key] || '—'}</p>
            </div>
          ))}
          <Button size="sm" variant="ghost" onClick={onDelete}>
            <Trash2 />
            Delete
          </Button>
        </div>
      )}
    </div>
  )
}

/** WOOP: Wish, Outcome, Obstacle, Plan. Guided fields, then the saved ones to reread. */
export function WoopTab() {
  const [draft, setDraft] = useState(EMPTY)
  const save = useSaveWoop()
  const list = useWoops()
  const del = useDeleteWoop()
  const pending = usePendingDelete((id) => del.mutate(id))
  const items = (list.data ?? []).filter((w) => !pending.hidden.has(w.id))

  return (
    <div className="mx-auto grid max-w-5xl gap-8 py-6 lg:grid-cols-[1fr_320px]" data-tour="motiv-plan">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          save.mutate(draft, {
            onSuccess: () => (setDraft(EMPTY), toast.success('WOOP saved')),
            onError: (err) => toast.error(err.message),
          })
        }}
      >
        <div className="space-y-1">
          <h2 className="text-base font-semibold">Plan with WOOP</h2>
          <p className="text-sm text-fg-muted">Dream it, then plan for what stops you. Naming the obstacle and an if-then plan makes the wish far more likely to happen.</p>
        </div>
        {FIELDS.map((f) => (
          <div key={f.key} className="space-y-1.5">
            <label htmlFor={`woop-${f.key}`} className="flex items-baseline gap-2">
              <span className="flex size-5 items-center justify-center rounded-sm bg-primary-subtle text-2xs font-semibold text-primary">{f.letter}</span>
              <span className="text-sm font-medium">{f.label}</span>
              <span className="text-xs text-fg-subtle">{f.help}</span>
            </label>
            <Textarea id={`woop-${f.key}`} value={draft[f.key]} onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value })} placeholder={f.placeholder} className="min-h-16" />
          </div>
        ))}
        <Button type="submit" variant="default" disabled={!draft.wish.trim() || save.isPending}>
          Save WOOP
        </Button>
      </form>
      <div className="space-y-2">
        <p className="text-xs font-medium text-fg-subtle">Your WOOPs</p>
        {list.isPending ? (
          <SkeletonRows rows={3} />
        ) : list.error ? (
          <ErrorState error={list.error} onRetry={() => list.refetch()} />
        ) : items.length === 0 ? (
          <p className="text-sm text-fg-muted">Saved WOOPs appear here so you can reread them when it gets hard.</p>
        ) : (
          items.map((w) => <SavedWoop key={w.id} woop={w} onDelete={() => pending.remove(w.id, 'WOOP')} />)
        )}
      </div>
    </div>
  )
}
