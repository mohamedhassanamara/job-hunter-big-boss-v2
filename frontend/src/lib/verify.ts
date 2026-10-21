import type { Tone } from '@/components/app/badges'
import type { ClaimVerdict, Verification, VerificationState } from '@/lib/types'

export const VERDICT: Record<ClaimVerdict, { label: string; tone: Tone; blocking: boolean }> = {
  supported: { label: 'Supported', tone: 'green', blocking: false },
  not_a_claim: { label: 'Not a claim', tone: 'gray', blocking: false },
  unsupported: { label: 'Not in your sources', tone: 'red', blocking: true },
  exaggerated: { label: 'Exaggerated', tone: 'red', blocking: true },
  merged: { label: 'Merged facts', tone: 'red', blocking: true },
  causal: { label: 'Adds a cause', tone: 'red', blocking: true },
  garbled: { label: 'Garbled sentence', tone: 'amber', blocking: false },
}

/** "pool:5" → "Experience #5", "signal:12" → "Company signal #12", … */
export function sourceLabel(id: string): string {
  if (!id) return ''
  const [kind, n] = id.split(':')
  return (
    { pool: `Experience #${n}`, signal: `Company signal #${n}`, cv: 'Approved CV', facts: 'Your facts', listing: 'The listing' }[kind] ?? id
  )
}

/** Gates (Copy, "I sent it") open only on a passed check of the current text. */
export const verified = (state: VerificationState | undefined) => state === 'passed'

export function stateTitle(state: VerificationState, v: Verification | undefined): string {
  switch (state) {
    case 'passed':
      return 'Every claim checked against your sources'
    case 'failed':
      return v?.blocking === 1 ? "1 claim doesn't hold" : `${v?.blocking ?? 0} claims don't hold`
    case 'error':
      return "The claim verifier couldn't run"
    case 'stale':
      return 'Changed since it was checked: check it again'
    default:
      return 'Not checked by the claim verifier yet'
  }
}
