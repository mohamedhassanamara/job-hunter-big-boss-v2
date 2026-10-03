import type { Streak, StreakDayState } from '@/lib/types'

/** One line about today, for the top bar tooltip and the Today card. */
export function todayLine(s: Streak): string {
  switch (s.today_state) {
    case 'met':
      return `Today's goal reached: ${s.today_count} of ${s.goal}.`
    case 'in_progress':
      return `${s.today_count} of ${s.goal} today. Today counts until midnight.`
    case 'weekend':
      return 'Weekend: your streak carries on by itself.'
    default:
      return `Weekend. Reach ${s.goal} on Monday to start a streak.`
  }
}

export const DAY_LABEL: Record<StreakDayState, string> = {
  met: 'goal reached',
  missed: 'goal missed',
  in_progress: 'today, in progress',
  weekend: 'weekend, counted',
  weekend_idle: 'weekend',
  idle: 'no streak yet',
  future: '',
}

export function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** mm:ss */
export function clock(seconds: number): string {
  const s = Math.max(0, Math.ceil(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}
