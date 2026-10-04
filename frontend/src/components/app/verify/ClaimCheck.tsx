import { CircleCheck, CircleX, LoaderCircle, ShieldCheck, TriangleAlert } from 'lucide-react'
import { ToneBadge } from '@/components/app/badges'
import { Button } from '@/components/ui/button'
import { relativeTime } from '@/lib/format'
import type { VerifiedClaim, Verification, VerificationState } from '@/lib/types'
import { cn } from '@/lib/utils'
import { sourceLabel, stateTitle, VERDICT } from '@/lib/verify'

function Claim({ c }: { c: VerifiedClaim }) {
  const v = VERDICT[c.verdict] ?? VERDICT.unsupported
  return (
    <li className="space-y-1 py-2">
      <div className="flex items-start gap-2">
        <ToneBadge tone={v.tone} dot={false} className="shrink-0">
          {v.label}
        </ToneBadge>
        <span className={cn('text-sm', v.blocking ? 'text-fg' : 'text-fg-muted')}>{c.claim}</span>
      </div>
      {(c.source_quote || c.reason) && (
        <div className="space-y-0.5 pl-1 text-xs text-fg-subtle">
          {c.source_quote && (
            <p>
              <span className="font-medium text-fg-muted">{sourceLabel(c.source_id)}:</span> <span className="italic">“{c.source_quote}”</span>
            </p>
          )}
          {c.reason && <p>{c.reason}</p>}
        </div>
      )}
    </li>
  )
}

/** The claim verifier on a text (Claude): each claim with its verdict, source quote and reason.
 * A passed check is tied to the exact text: any edit makes it stale. */
export function ClaimCheck({
  verification,
  state,
  onVerify,
  verifying,
  gate,
  compact,
}: {
  verification: Verification | undefined
  state: VerificationState
  onVerify?: () => void
  verifying?: boolean
  /** What a passed check unlocks, e.g. "approval" or "Copy". */
  gate: string
  compact?: boolean
}) {
  const claims = verification?.claims ?? []
  const blocking = claims.filter((c) => VERDICT[c.verdict]?.blocking ?? true)
  const rest = claims.filter((c) => !(VERDICT[c.verdict]?.blocking ?? true))
  const Icon = verifying ? LoaderCircle : state === 'passed' ? CircleCheck : state === 'failed' ? CircleX : state === 'none' ? ShieldCheck : TriangleAlert
  const tone =
    state === 'passed' ? 'border-tone-green-border bg-success-bg text-success-fg' : state === 'failed' ? 'border-tone-red-border bg-danger-bg text-danger-fg' : state === 'none' ? 'border-border bg-surface text-fg-muted' : 'border-tone-amber-border bg-warning-bg text-warning-fg'
  const meta = verification?.at && state !== 'none' ? [verification.model, verification.duration_ms ? `${Math.round(verification.duration_ms / 1000)} s` : null, relativeTime(verification.at)].filter(Boolean).join(' · ') : null
  return (
    <section className="space-y-0 rounded-md border border-border bg-surface" data-tour="claim-check">
      <div className={cn('flex items-center gap-2 rounded-t-md border-b px-3 py-2 text-sm', tone, !claims.length && 'rounded-b-md border-b-0')}>
        <Icon className={cn('size-4 shrink-0', verifying && 'animate-spin')} />
        <span className="min-w-0 flex-1">
          <span className="font-medium">{verifying ? 'Checking every claim against your sources…' : stateTitle(state, verification)}</span>
          {!verifying && state === 'error' && verification?.error && <span className="block text-xs">{verification.error}</span>}
          {!verifying && state !== 'passed' && <span className="block text-xs opacity-80">Claude must pass it before {gate}.</span>}
          {meta && !verifying && <span className="block text-xs opacity-80">{meta}</span>}
        </span>
        {onVerify && (
          <Button size="xs" variant="secondary" onClick={onVerify} disabled={verifying}>
            {state === 'none' ? 'Check claims' : 'Check again'}
          </Button>
        )}
      </div>
      {claims.length > 0 && !verifying && (
        <div className={cn('px-3', compact ? 'py-1' : 'py-1.5')}>
          {blocking.length > 0 && <ul className="divide-y divide-border">{blocking.map((c, i) => <Claim key={`b${i}`} c={c} />)}</ul>}
          {rest.length > 0 && (
            <details className="py-1.5" open={blocking.length === 0 && !compact}>
              <summary className="cursor-default text-xs font-medium text-fg-subtle">
                {blocking.length ? `The other ${rest.length} claims` : `All ${rest.length} claims`}
              </summary>
              <ul className="divide-y divide-border">{rest.map((c, i) => <Claim key={`r${i}`} c={c} />)}</ul>
            </details>
          )}
        </div>
      )}
    </section>
  )
}
