import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Verification, VerificationState } from '@/lib/types'
import { invalidateWork } from './keys'

/** Which text the fixes edit: an email draft, a cover letter / form text, a form answer, or a
 * LinkedIn note, follow-up or InMail of one person. */
export interface FixTarget {
  kind: 'email' | 'letter' | 'answer' | 'linkedin'
  id: number
  sub?: 'note' | 'followup' | 'inmail'
}

export interface FixItem {
  sentence: string
  /** "" removes the sentence. */
  replacement: string
}

/** Apply suggested fixes, then re-verify only the sentences they changed (Claude, one short call). */
export function useApplyClaimFixes() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ target, fixes }: { target: FixTarget; fixes: FixItem[] }) =>
      api.post<{ verification: Verification; verification_state: VerificationState }>('/claim-fixes/apply', { kind: target.kind, id: target.id, sub: target.sub ?? '', fixes }),
    onSettled: () => {
      invalidateWork(qc)
      for (const key of ['answers', 'linkedin']) void qc.invalidateQueries({ queryKey: [key] })
    },
  })
}
