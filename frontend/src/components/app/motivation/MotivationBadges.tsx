import { Coins, Flame } from 'lucide-react'
import { useNavigate } from 'react-router'
import { Tooltip } from '@/components/ui/tooltip'
import { plural, todayLine } from '@/lib/motivation'
import { useMotivation } from '@/lib/queries/motivation'
import { cn } from '@/lib/utils'

/** Top bar: the workday streak with today's progress, and the token balance. Hidden when
 * Settings → Motivation is off. */
export function MotivationBadges() {
  const { data } = useMotivation()
  const navigate = useNavigate()
  if (!data?.enabled) return null
  const s = data.streak
  const met = s.today_state === 'met'
  const weekend = s.today_state === 'weekend' || s.today_state === 'weekend_idle'
  return (
    <div className="flex items-center gap-0.5" data-tour="motivation-badges">
      <Tooltip content={`Streak: ${plural(s.current, 'day')} (longest ${s.longest}). ${todayLine(s)}`}>
        <button
          onClick={() => navigate('/motivation?tab=wins')}
          aria-label={`Streak ${s.current} days, ${s.today_count} of ${s.goal} today`}
          className="flex h-8 items-center gap-1.5 rounded-md px-2 text-sm transition-colors duration-120 hover:bg-surface-hover"
        >
          <Flame className={cn('size-4', s.current > 0 || met ? 'text-tone-amber-dot' : 'text-fg-subtle')} />
          <span className="font-medium tabular-nums">{s.current}</span>
          {!weekend && (
            <span className={cn('rounded-sm px-1 text-2xs font-medium tabular-nums', met ? 'bg-tone-amber-bg text-tone-amber-fg' : 'bg-bg-subtle text-fg-muted')}>
              {Math.min(s.today_count, 999)}/{s.goal}
            </span>
          )}
        </button>
      </Tooltip>
      <Tooltip content={`${plural(data.tokens, 'token')} to spend in your shop${data.chests.available ? ` · ${plural(data.chests.available, 'chest')} waiting` : ''}`}>
        <button
          onClick={() => navigate('/motivation?tab=shop')}
          aria-label={`${data.tokens} tokens`}
          className="relative flex h-8 items-center gap-1.5 rounded-md px-2 text-sm transition-colors duration-120 hover:bg-surface-hover"
        >
          <Coins className="size-4 text-tone-violet-dot" />
          <span className="font-medium tabular-nums">{data.tokens}</span>
          {data.chests.available > 0 && <span className="absolute top-1.5 right-1 size-1.5 rounded-full bg-tone-violet-dot" />}
        </button>
      </Tooltip>
    </div>
  )
}
