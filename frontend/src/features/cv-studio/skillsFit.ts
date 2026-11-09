import type { CVSkillsFit } from '@/lib/types'

/** One line about the skills line: "17 skills · 2 lines · last line 78% full". */
export function fitSummary(fit: CVSkillsFit): string {
  const parts = [`${fit.count} skill${fit.count === 1 ? '' : 's'}`]
  if (fit.lines != null) parts.push(`${fit.lines} line${fit.lines === 1 ? '' : 's'}`)
  if (fit.lines != null && fit.lines > 1 && fit.last_fill != null) parts.push(`last line ${Math.round(fit.last_fill * 100)}% full`)
  return parts.join(' · ')
}
