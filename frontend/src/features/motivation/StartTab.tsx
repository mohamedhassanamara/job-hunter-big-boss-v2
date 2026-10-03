import { ArrowRight, Lightbulb, Pause, Play, Square } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Kbd } from '@/components/ui/kbd'
import { Skeleton } from '@/components/ui/skeleton'
import { useCountdown } from '@/hooks/useCountdown'
import { useHotkeys } from '@/hooks/useHotkeys'
import { clock } from '@/lib/motivation'
import { useSuggestion } from '@/lib/queries/motivation'

type Step = 'pick' | 'focus' | 'end' | 'finished'

/** The 5-minute rule: pick one tiny task, work on it for 5 minutes, then decide. */
export function StartTab() {
  const suggestion = useSuggestion()
  const [task, setTask] = useState('')
  const [step, setStep] = useState<Step>('pick')
  const [round, setRound] = useState(0)
  const timer = useCountdown(() => setStep('end'))
  const chosen = task.trim() || suggestion.data?.label || ''

  const begin = (minutes: number) => {
    setStep('focus')
    setRound((r) => r + 1)
    timer.start(minutes * 60)
  }
  useHotkeys(
    {
      ' ': () => step === 'focus' && (timer.running ? timer.pause() : timer.resume()),
      // A focused button already handles Enter itself.
      enter: (e) => step === 'pick' && chosen && (e.target as HTMLElement).tagName !== 'BUTTON' && begin(5),
    },
    { allowInInputs: false },
  )

  const pct = timer.total ? 1 - timer.left / timer.total : 0
  const R = 88
  const C = 2 * Math.PI * R

  if (step === 'pick') {
    return (
      <div className="mx-auto max-w-xl space-y-5 py-6" data-tour="motiv-start">
        <div className="space-y-1">
          <h2 className="text-base font-semibold">Start with five minutes</h2>
          <p className="text-sm text-fg-muted">Pick one tiny task and give it five minutes. Starting is the hard part; after that, you decide whether to keep going.</p>
        </div>
        <div className="rounded-lg border border-border bg-surface p-4">
          <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-fg-subtle">
            <Lightbulb className="size-3.5" />
            Suggested from your queue
          </p>
          {suggestion.isPending ? (
            <Skeleton className="h-10" />
          ) : suggestion.data ? (
            <div className="flex items-center gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{suggestion.data.label}</p>
                <p className="truncate text-xs text-fg-muted">{suggestion.data.detail}</p>
              </div>
              <Button size="sm" variant="ghost" asChild>
                <Link to={suggestion.data.href}>
                  Open
                  <ArrowRight />
                </Link>
              </Button>
            </div>
          ) : (
            <p className="text-sm text-fg-muted">Nothing suggested right now: type your own task below.</p>
          )}
        </div>
        <div className="space-y-1.5">
          <label htmlFor="own-task" className="text-xs font-medium text-fg-subtle">
            Or your own tiny task
          </label>
          <Input id="own-task" value={task} onChange={(e) => setTask(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && chosen && begin(5)} placeholder="e.g. Write the first line of one cover letter" />
        </div>
        <Button variant="default" onClick={() => begin(5)} disabled={!chosen}>
          <Play />
          Start 5 minutes
          <Kbd className="ml-1">Enter</Kbd>
        </Button>
      </div>
    )
  }

  return (
    <div className="mx-auto flex max-w-xl flex-col items-center gap-5 py-6 text-center" data-tour="motiv-start">
      <p className="text-sm text-fg-muted">
        {step === 'focus' ? 'Focus on' : 'You worked on'} <span className="font-medium text-fg">{chosen}</span>
      </p>
      <div className="relative flex size-52 items-center justify-center">
        <svg viewBox="0 0 200 200" className="absolute inset-0 -rotate-90" aria-hidden>
          <circle cx="100" cy="100" r={R} fill="none" strokeWidth="8" className="stroke-bg-subtle" />
          <circle cx="100" cy="100" r={R} fill="none" strokeWidth="8" strokeLinecap="round" className="stroke-primary transition-[stroke-dashoffset] duration-200" strokeDasharray={C} strokeDashoffset={C * (1 - pct)} />
        </svg>
        <div>
          <p className="text-2xl font-semibold tabular-nums" aria-live="off">
            {step === 'focus' ? clock(timer.left) : '0:00'}
          </p>
          <p className="text-xs text-fg-subtle">{round > 1 ? 'Keep-going round' : 'Five minutes'}</p>
        </div>
      </div>
      {step === 'focus' && (
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => (timer.running ? timer.pause() : timer.resume())}>
            {timer.running ? <Pause /> : <Play />}
            {timer.running ? 'Pause' : 'Resume'}
            <Kbd className="ml-1">Space</Kbd>
          </Button>
          <Button variant="ghost" onClick={() => (timer.stop(), setStep('end'))}>
            <Square />
            Stop here
          </Button>
        </div>
      )}
      {step === 'end' && (
        <div className="space-y-3">
          <p className="text-base font-medium">You started. That was the hard part.</p>
          <div className="flex justify-center gap-2">
            <Button variant="ghost" onClick={() => setStep('finished')}>
              Done for now
            </Button>
            <Button variant="default" onClick={() => begin(25)}>
              Keep going (25 min)
            </Button>
          </div>
        </div>
      )}
      {step === 'finished' && (
        <div className="space-y-3">
          <p className="text-base font-medium">Good work. Small steps add up.</p>
          <Button variant="secondary" onClick={() => (setStep('pick'), setTask(''), setRound(0), void suggestion.refetch())}>
            Pick another task
          </Button>
        </div>
      )}
    </div>
  )
}
