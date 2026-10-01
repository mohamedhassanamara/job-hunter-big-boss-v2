import { MessageSquareWarning } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { relativeTime } from '@/lib/format'
import { type CritiqueKind, useCritique } from '@/lib/queries/critique'

/** "Critique": one Claude call listing what's still weak from the reader's side. It never
 * rewrites anything; you decide what to change. */
export function CritiqueButton({ kind, id, size = 'sm' }: { kind: CritiqueKind; id: number; size?: 'sm' | 'xs' }) {
  const run = useCritique()
  const [open, setOpen] = useState(false)
  const data = run.data
  const start = () => run.mutate({ kind, id }, { onError: (e) => (toast.error(e.message), setOpen(false)) })
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          size={size}
          variant="ghost"
          onClick={() => {
            if (!data && !run.isPending) start()
          }}
          data-tour="critique"
        >
          <MessageSquareWarning />
          {run.isPending ? 'Reading it…' : 'Critique'}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-96 space-y-2 p-3">
        {run.isPending ? (
          <p className="text-sm text-fg-muted">Claude is reading it as the recipient would…</p>
        ) : data ? (
          <>
            <p className="text-xs font-medium text-fg-subtle">What's still weak, from the reader's side (nothing is changed)</p>
            {data.issues.length === 0 ? (
              <p className="text-sm">Nothing weak found.</p>
            ) : (
              <ol className="space-y-2">
                {data.issues.map((i, n) => (
                  <li key={n} className="text-sm">
                    <span className="text-xs font-medium text-fg-subtle">{i.where}</span>
                    <p>{i.issue}</p>
                    <p className="text-xs text-fg-muted">{i.why}</p>
                  </li>
                ))}
              </ol>
            )}
            <div className="flex items-center gap-2 border-t border-border pt-2 text-2xs text-fg-subtle">
              {data.model} · {relativeTime(data.created_at)}
              <Button size="xs" variant="ghost" className="ml-auto" disabled={run.isPending} onClick={start}>
                Critique again
              </Button>
            </div>
          </>
        ) : null}
      </PopoverContent>
    </Popover>
  )
}
