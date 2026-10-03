import { Pause, Play, Square, Volume2, VolumeX } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Kbd } from '@/components/ui/kbd'
import { SegmentedList, SegmentedTrigger } from '@/components/ui/tabs'
import { Tabs } from '@/components/ui/tabs'
import { useHotkeys } from '@/hooks/useHotkeys'
import { CYCLE_SECONDS, PHASES, phaseAt, playTone } from '@/lib/breathing'
import { clock, prefersReducedMotion } from '@/lib/motivation'
import { cn } from '@/lib/utils'

type Status = 'idle' | 'running' | 'paused' | 'done'

/** Guided cyclic sighing: an animated circle with cues, 1, 3 or 5 minutes, optional soft tones.
 * Space pauses or resumes, Escape stops. */
export function BreatheTab() {
  const [minutes, setMinutes] = useState(5)
  const [sound, setSound] = useState(false)
  const [status, setStatus] = useState<Status>('idle')
  const [elapsed, setElapsed] = useState(0)
  const base = useRef(0) // seconds done before the current run segment
  const since = useRef(0) // performance.now() when the segment started
  const phaseRef = useRef(-1)
  const audio = useRef<AudioContext | null>(null)
  const reduced = prefersReducedMotion()
  const total = minutes * 60

  useEffect(() => {
    if (status !== 'running') return
    let frame = 0
    const tick = (now: number) => {
      const t = base.current + (now - since.current) / 1000
      if (t >= total) {
        setElapsed(total)
        setStatus('done')
        return
      }
      setElapsed(t)
      const { index, cycle } = phaseAt(t)
      const key = cycle * 10 + index
      if (key !== phaseRef.current) {
        phaseRef.current = key
        if (sound && audio.current) playTone(audio.current, PHASES[index].tone, PHASES[index].seconds)
      }
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [status, total, sound])

  const start = () => {
    if (sound && !audio.current) audio.current = new AudioContext()
    base.current = 0
    phaseRef.current = -1
    since.current = performance.now()
    setElapsed(0)
    setStatus('running')
  }
  const toggle = () => {
    if (status === 'running') {
      base.current = elapsed
      setStatus('paused')
    } else if (status === 'paused') {
      since.current = performance.now()
      phaseRef.current = -1
      setStatus('running')
    } else start()
  }
  const stop = () => {
    setStatus('idle')
    setElapsed(0)
  }
  useHotkeys({ ' ': toggle, escape: () => status !== 'idle' && stop() })

  const phase = phaseAt(elapsed)
  const active = status === 'running' || status === 'paused'
  const cue = status === 'done' ? 'Well done. Notice how you feel.' : active ? PHASES[phase.index].cue : 'Two inhales through the nose, one long exhale through the mouth.'

  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center gap-6 py-6" data-tour="motiv-breathe">
      <div className="relative flex size-72 items-center justify-center">
        <div className="absolute inset-0 rounded-full border border-dashed border-tone-teal-border" />
        <div
          className={cn('absolute inset-0 rounded-full bg-tone-teal-bg', !reduced && 'will-change-transform')}
          style={{ transform: `scale(${reduced || !active ? 0.75 : phase.scale})` }}
        />
        <div className="relative space-y-1 px-10 text-center">
          <p className="text-base font-medium text-tone-teal-fg" aria-live="polite">
            {cue}
          </p>
          {active && <p className="text-xs text-fg-subtle tabular-nums">Cycle {phase.cycle + 1}</p>}
        </div>
      </div>
      {active && reduced && (
        <div className="h-1.5 w-64 overflow-hidden rounded-full bg-bg-subtle" aria-hidden>
          <div className="h-full bg-tone-teal-dot" style={{ width: `${phase.progress * 100}%` }} />
        </div>
      )}
      <div className="w-full max-w-sm space-y-1.5">
        <div className="h-1 overflow-hidden rounded-full bg-bg-subtle">
          <div className="h-full bg-tone-teal-dot transition-[width] duration-200" style={{ width: `${(elapsed / total) * 100}%` }} />
        </div>
        <p className="flex justify-between text-xs text-fg-subtle tabular-nums">
          <span>{clock(elapsed)}</span>
          <span>{clock(total - elapsed)} left</span>
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-3">
        <Tabs value={String(minutes)} onValueChange={(v) => !active && setMinutes(Number(v))}>
          <SegmentedList aria-label="Duration">
            {[1, 3, 5].map((m) => (
              <SegmentedTrigger key={m} value={String(m)} disabled={active}>
                {m} min
              </SegmentedTrigger>
            ))}
          </SegmentedList>
        </Tabs>
        <Button variant={status === 'running' ? 'secondary' : 'default'} onClick={toggle}>
          {status === 'running' ? <Pause /> : <Play />}
          {status === 'running' ? 'Pause' : status === 'paused' ? 'Resume' : status === 'done' ? 'Again' : 'Start'}
          <Kbd className="ml-1">Space</Kbd>
        </Button>
        {active && (
          <Button variant="ghost" onClick={stop}>
            <Square />
            Stop
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon"
          aria-pressed={sound}
          aria-label={sound ? 'Turn the sound off' : 'Turn on a soft sound'}
          onClick={() => {
            if (!sound && !audio.current) audio.current = new AudioContext()
            setSound((v) => !v)
          }}
        >
          {sound ? <Volume2 /> : <VolumeX />}
        </Button>
      </div>
      <p className="max-w-md text-center text-xs text-fg-subtle">
        One cycle is {CYCLE_SECONDS} seconds: inhale 2s, top up 1s, exhale 6s. A few minutes of slow exhales calm the body. Stop any time if you feel dizzy.
      </p>
    </div>
  )
}
