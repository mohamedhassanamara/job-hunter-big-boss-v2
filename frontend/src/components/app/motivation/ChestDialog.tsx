import { Coins, Package, PackageOpen } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { plural, prefersReducedMotion } from '@/lib/motivation'
import { useOpenChest, useRefreshMotivation } from '@/lib/queries/motivation'
import { cn } from '@/lib/utils'

type Phase = 'shaking' | 'counting' | 'done' | 'error'
const SPARKS = Array.from({ length: 10 }, (_, i) => {
  const angle = (i / 10) * Math.PI * 2
  return { dx: `${Math.round(Math.cos(angle) * 90)}px`, dy: `${Math.round(Math.sin(angle) * 70 - 20)}px` }
})

/** Opens one chest: the server draws 1-10 tokens first, then a short shake and a count-up show
 * it. Click "Skip" (or anywhere on the chest) to jump to the result; reduced motion shows it
 * at once. */
function ChestReveal({ onClose, onAnother }: { onClose: () => void; onAnother: () => void }) {
  const open = useOpenChest()
  const [phase, setPhase] = useState<Phase>('shaking')
  const [shown, setShown] = useState(0)
  const [result, setResult] = useState<{ tokens: number; balance: number; left: number } | null>(null)
  const frame = useRef(0)
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return
    started.current = true
    const begin = Date.now()
    open.mutate(undefined, {
      onSuccess: (r) => {
        setResult({ tokens: r.chest.tokens, balance: r.balance, left: r.chests.available })
        const wait = prefersReducedMotion() ? 0 : Math.max(0, 600 - (Date.now() - begin))
        window.setTimeout(() => setPhase((p) => (p === 'done' ? p : prefersReducedMotion() ? 'done' : 'counting')), wait)
      },
      onError: () => setPhase('error'),
    })
  }, [open])

  useEffect(() => {
    if (phase !== 'counting' || !result) return
    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / 600)
      setShown(Math.round(result.tokens * (1 - (1 - t) ** 3)))
      if (t < 1) frame.current = requestAnimationFrame(tick)
      else setPhase('done')
    }
    frame.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame.current)
  }, [phase, result])

  const skip = () => result && setPhase('done')
  const value = phase === 'done' ? (result?.tokens ?? 0) : shown
  const opened = phase === 'counting' || phase === 'done'

  return (
    <div className="flex flex-col items-center gap-4 px-6 pt-8 pb-6 text-center">
      <button type="button" onClick={skip} aria-label="Skip the animation" className="relative flex size-32 items-center justify-center rounded-full bg-tone-violet-bg">
        {opened ? (
          <PackageOpen className="size-16 animate-chest-pop text-tone-violet-fg" strokeWidth={1.5} />
        ) : (
          <Package className={cn('size-16 text-tone-violet-fg', phase === 'shaking' && 'animate-chest-shake [animation-iteration-count:infinite]')} strokeWidth={1.5} />
        )}
        {phase === 'counting' &&
          SPARKS.map((s, i) => (
            <span
              key={i}
              className="absolute top-1/2 left-1/2 size-2 animate-token-rise rounded-full bg-tone-amber-dot"
              style={{ '--dx': s.dx, '--dy': s.dy } as React.CSSProperties}
            />
          ))}
      </button>
      {phase === 'error' ? (
        <p className="text-sm text-danger-fg">{open.error?.message ?? 'The chest could not be opened'}</p>
      ) : (
        <div aria-live="polite" className="space-y-1">
          <p className="flex items-center justify-center gap-2 text-2xl font-semibold tabular-nums">
            <Coins className="size-6 text-tone-violet-dot" />
            {opened ? `+${value}` : '…'}
          </p>
          <p className="text-sm text-fg-muted">
            {phase === 'done' && result ? `${plural(result.tokens, 'token')} won. Balance: ${result.balance}.` : 'Opening your chest…'}
          </p>
        </div>
      )}
      <div className="flex gap-2">
        {phase === 'done' && result && result.left > 0 ? (
          <>
            <Button variant="ghost" onClick={onClose}>
              Close
            </Button>
            <Button variant="default" onClick={onAnother}>
              Open the next one ({result.left})
            </Button>
          </>
        ) : phase === 'done' || phase === 'error' ? (
          <Button variant="default" onClick={onClose} autoFocus>
            Nice
          </Button>
        ) : (
          <Button variant="ghost" size="sm" onClick={skip} disabled={!result}>
            Skip
          </Button>
        )}
      </div>
    </div>
  )
}

export function ChestDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [round, setRound] = useState(0)
  const refresh = useRefreshMotivation()
  const change = (next: boolean) => {
    if (!next) refresh()
    onOpenChange(next)
  }
  return (
    <Dialog open={open} onOpenChange={change}>
      <DialogContent title="Open your chest" className="max-w-sm" data-tour="chest-dialog">
        {open && <ChestReveal key={round} onClose={() => change(false)} onAnother={() => setRound((r) => r + 1)} />}
      </DialogContent>
    </Dialog>
  )
}
