import type { CVVersion } from '@/lib/types'

/** The Approve gate, the same rule as the backend (`api/cv.py:approve_cv`): exactly one page and no
 * bullet, skill, number or tool error. Summary checks inform, they never block. */
export function approveGate(version: CVVersion | undefined) {
  const onePage = version?.page_count === 1 && !version.error
  const errors = (version?.violations ?? []).filter((v) => v.severity === 'error' && v.where !== 'summary')
  return { onePage: Boolean(onePage), errors }
}
