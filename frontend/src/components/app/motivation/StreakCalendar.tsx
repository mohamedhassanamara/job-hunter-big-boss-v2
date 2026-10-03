import { DAY_LABEL } from '@/lib/motivation'
import type { StreakDay, StreakDayState } from '@/lib/types'
import { cn } from '@/lib/utils'

const CELL: Record<StreakDayState, string> = {
  met: 'bg-tone-amber-dot',
  weekend: 'bg-tone-amber-bg border border-tone-amber-border',
  missed: 'bg-surface-hover',
  in_progress: 'bg-bg-subtle ring-1 ring-primary',
  weekend_idle: 'bg-bg-subtle',
  idle: 'bg-bg-subtle',
  future: 'border border-dashed border-border',
}
const WEEKDAYS = ['Mon', '', 'Wed', '', 'Fri', '', 'Sun']

/** The last weeks, one column per week (Monday on top), like a contribution graph. */
export function StreakCalendar({ days }: { days: StreakDay[] }) {
  const weeks: StreakDay[][] = []
  for (let i = 0; i < days.length; i += 7) weeks.push(days.slice(i, i + 7))
  const fmt = new Intl.DateTimeFormat(undefined, { weekday: 'short', day: 'numeric', month: 'short' })
  return (
    <div className="flex gap-1.5" role="img" aria-label="Streak calendar of the last weeks">
      <div className="flex flex-col gap-1 pr-0.5 text-2xs leading-3.5 text-fg-subtle">
        {WEEKDAYS.map((d, i) => (
          <span key={i} className="h-3.5">
            {d}
          </span>
        ))}
      </div>
      {weeks.map((week) => (
        <div key={week[0].day} className="flex flex-col gap-1">
          {week.map((d) => (
            <span
              key={d.day}
              title={d.state === 'future' ? undefined : `${fmt.format(new Date(`${d.day}T12:00:00`))} · ${d.count} · ${DAY_LABEL[d.state]}`}
              className={cn('size-3.5 rounded-sm', CELL[d.state])}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

export function CalendarLegend() {
  const items: [StreakDayState, string][] = [
    ['met', 'Goal reached'],
    ['weekend', 'Weekend, counted'],
    ['missed', 'Missed'],
    ['in_progress', 'Today'],
  ]
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 text-2xs text-fg-subtle">
      {items.map(([state, label]) => (
        <span key={state} className="flex items-center gap-1">
          <span className={cn('size-2.5 rounded-sm', CELL[state])} />
          {label}
        </span>
      ))}
    </div>
  )
}
