import type { JobFilters } from '@/lib/queries/jobs'

export function hasActiveFilters(f: JobFilters) {
  return !!(
    f.q ||
    f.source?.length ||
    f.remote?.length ||
    f.country?.length ||
    f.min_score ||
    f.posted_within ||
    f.hide_duplicates ||
    f.label ||
    f.flags
  )
}
