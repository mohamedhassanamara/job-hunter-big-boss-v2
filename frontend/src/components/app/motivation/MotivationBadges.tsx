import { Coins, Droplet, Flame } from 'lucide-react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { Tooltip } from '@/components/ui/tooltip'
import { plural, todayLine } from '@/lib/motivation'
import { useMotivation, useUseFreeze } from '@/lib/queries/motivation'
import type { FreezeShop } from '@/lib/types'
import { cn } from '@/lib/utils'

/** The drop under the streak (hover or keyboard focus): one click freezes today. With none owned
 * it shows the price and opens the shop card; otherwise a disabled state says why. */
function FreezeControl({ freeze }: { freeze: FreezeShop }) {
  const use = useUseFreeze()
  const navigate = useNavigate()
  const none = freeze.use === 'none_owned'
  const available = freeze.use === 'available'
  const label = none ? `Freeze streak · none owned · ${plural(freeze.price, 'token')}` : `Freeze streak · ${freeze.owned} owned`
  return (
    <button
      type="button"
      disabled={!available && !none}
      title={!available && !none ? (freeze.use_reason ?? undefined) : undefined}
      aria-label={!available && !none ? `Freeze streak: ${freeze.use_reason}` : label}
      onClick={() => {
        if (none) return navigate('/motivation?tab=shop#freeze')
        use.mutate(undefined, { onSuccess: () => toast.success('Today is frozen: your streak goes up by one'), onError: (e) => toast.error(e.message) })
      }}
      className="flex h-8 items-center gap-2 rounded-md border border-border bg-surface px-2.5 text-sm whitespace-nowrap shadow-sm transition-colors duration-120 hover:bg-surface-hover disabled:cursor-not-allowed disabled:text-fg-subtle disabled:hover:bg-surface"
    >
      <Droplet className="size-4 text-tone-blue-dot" />
      <span>Freeze streak</span>
      <span className="text-xs text-fg-muted">
        {available ? `${freeze.owned} owned` : none ? `none · ${plural(freeze.price, 'token')}` : freeze.use_reason}
      </span>
    </button>
  )
}

/** Top bar: the workday streak with today's progress, and the token balance. Hidden when
 * Settings → Motivation is off. */
export function MotivationBadges() {
  const { data } = useMotivation()
  const navigate = useNavigate()
  if (!data?.enabled) return null
  const s = data.streak
  const met = s.today_state === 'met'
  const weekend = s.today_state === 'weekend' || s.today_state === 'weekend_idle'
  const frozen = s.today_state === 'freeze'
  return (
    <div className="flex items-center gap-0.5" data-tour="motivation-badges">
      <div className="group relative">
        <Tooltip side="left" content={`Streak: ${plural(s.current, 'day')} (longest ${s.longest}). ${todayLine(s)}`}>
          <button
            onClick={() => navigate('/motivation?tab=wins')}
            aria-label={`Streak ${s.current} days, ${s.today_count} of ${s.goal} today`}
            className="flex h-8 items-center gap-1.5 rounded-md px-2 text-sm transition-colors duration-120 hover:bg-surface-hover"
          >
            <Flame className={cn('size-4', s.current > 0 || met || frozen ? 'text-tone-amber-dot' : 'text-fg-subtle')} />
            <span className="font-medium tabular-nums">{s.current}</span>
            {!weekend && (
              <span className={cn('rounded-sm px-1 text-2xs font-medium tabular-nums', met || frozen ? 'bg-tone-amber-bg text-tone-amber-fg' : 'bg-bg-subtle text-fg-muted')}>
                {frozen ? 'frozen' : `${Math.min(s.today_count, 999)}/${s.goal}`}
              </span>
            )}
          </button>
        </Tooltip>
        <div className="invisible absolute top-full left-0 z-40 pt-1 group-focus-within:visible group-hover:visible" data-tour="streak-freeze">
          <FreezeControl freeze={data.freeze} />
        </div>
      </div>
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
