import { Package } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { plural, todayLine } from '@/lib/motivation'
import type { MotivationSummary } from '@/lib/types'
import { cn } from '@/lib/utils'
import { ChestDialog } from './ChestDialog'
import { CalendarLegend, StreakCalendar } from './StreakCalendar'

/** Today: the streak (current, longest, today's progress) and the last weeks. */
export function StreakSummary({ data }: { data: MotivationSummary }) {
  const s = data.streak
  const pct = Math.min(100, Math.round((s.today_count / s.goal) * 100))
  const weekend = s.today_state === 'weekend' || s.today_state === 'weekend_idle'
  return (
    <div className="space-y-3 p-4">
      <div className="flex items-end gap-6">
        <div>
          <p className="text-2xl font-semibold tabular-nums">{s.current}</p>
          <p className="text-xs text-fg-subtle">{s.current === 1 ? 'day in a row' : 'days in a row'}</p>
        </div>
        <div>
          <p className="text-lg font-medium text-fg-muted tabular-nums">{s.longest}</p>
          <p className="text-xs text-fg-subtle">longest</p>
        </div>
        {!weekend && (
          <div className="ml-auto min-w-28 flex-1 space-y-1">
            <p className="text-right text-xs text-fg-muted tabular-nums">
              {s.today_count} / {s.goal} today
            </p>
            <div className="h-1.5 overflow-hidden rounded-full bg-bg-subtle">
              <div className={cn('h-full rounded-full transition-[width] duration-200', s.today_state === 'met' ? 'bg-tone-amber-dot' : 'bg-primary')} style={{ width: `${pct}%` }} />
            </div>
          </div>
        )}
      </div>
      <p className="text-xs text-fg-muted">{todayLine(s)}</p>
      <StreakCalendar days={s.calendar} />
      <CalendarLegend />
    </div>
  )
}

/** Today: progress to the next chest, and the chests waiting to be opened. */
export function ChestSummary({ data }: { data: MotivationSummary }) {
  const [opening, setOpening] = useState(false)
  const c = data.chests
  const pct = Math.min(100, Math.round((c.progress / c.goal) * 100))
  return (
    <div className="space-y-3 p-4">
      <div className="flex items-center gap-3">
        <span className={cn('flex size-10 shrink-0 items-center justify-center rounded-lg', c.available ? 'bg-tone-violet-bg text-tone-violet-fg' : 'bg-bg-subtle text-fg-subtle')}>
          <Package className={cn('size-5', c.available && 'animate-chest-shake')} />
        </span>
        <div className="min-w-0 flex-1 space-y-1">
          <p className="text-sm">
            {c.available ? (
              <span className="font-medium">{c.available === 1 ? 'A chest is waiting' : `${c.available} chests are waiting`}</span>
            ) : (
              <>
                <span className="font-medium tabular-nums">
                  {c.progress} / {c.goal}
                </span>{' '}
                <span className="text-fg-muted">applications to the next chest</span>
              </>
            )}
          </p>
          <div className="h-1.5 overflow-hidden rounded-full bg-bg-subtle">
            <div className="h-full rounded-full bg-tone-violet-dot transition-[width] duration-200" style={{ width: `${c.available ? 100 : pct}%` }} />
          </div>
        </div>
        {c.available > 0 && (
          <Button size="sm" variant="secondary" onClick={() => setOpening(true)}>
            Open
          </Button>
        )}
      </div>
      <p className="text-xs text-fg-subtle">
        {plural(c.opened, 'chest')} opened · {plural(data.tokens, 'token')} to spend
      </p>
      <ChestDialog open={opening} onOpenChange={setOpening} />
    </div>
  )
}
