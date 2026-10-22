import { CircleCheck, CircleX, LoaderCircle, ShieldCheck, TriangleAlert, WandSparkles } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { ToneBadge } from '@/components/app/badges'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'
import { relativeTime } from '@/lib/format'
import { type FixItem, type FixTarget, useApplyClaimFixes } from '@/lib/queries/claimFixes'
import type { VerifiedClaim, Verification, VerificationState } from '@/lib/types'
import { cn } from '@/lib/utils'
import { sourceLabel, stateTitle, VERDICT } from '@/lib/verify'

/** The suggested fix of one flagged claim: what it relies on, and Apply / Edit then apply / Ignore.
 * Applying edits the text and re-checks only the changed sentence. */
function FixCard({ c, busy, onApply, onIgnore }: { c: VerifiedClaim; busy: boolean; onApply: (replacement: string) => void; onIgnore: () => void }) {
  const fix = c.fix
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(fix?.text ?? '')
  if (!fix) return null
  const remove = fix.kind === 'remove'
  return (
    <div className="ml-1 space-y-2 rounded-md border border-border bg-bg-subtle p-2.5 text-xs" data-tour="claim-fix">
      <p className="font-medium text-fg-muted">{remove ? 'Suggested fix: remove this sentence' : 'Suggested fix'}</p>
      {editing ? (
        <Textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={3} aria-label="Edit the suggested sentence" />
      ) : (
        !remove && <p className="text-sm text-fg">{fix.text}</p>
      )}
      {fix.source_quote && !editing && (
        <p className="text-fg-subtle">
          <span className="font-medium text-fg-muted">{sourceLabel(fix.source_id)}:</span> <span className="italic">“{fix.source_quote}”</span>
        </p>
      )}
      {fix.note && !editing && <p className="text-fg-subtle">{fix.note}</p>}
      <div className="flex flex-wrap items-center gap-2">
        {editing ? (
          <>
            <Button size="xs" variant="secondary" disabled={busy} onClick={() => onApply(draft.trim())}>
              {draft.trim() ? 'Apply edit' : 'Remove sentence'}
            </Button>
            <Button size="xs" variant="ghost" disabled={busy} onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </>
        ) : (
          <>
            <Button size="xs" variant="secondary" disabled={busy} onClick={() => onApply(fix.text)}>
              {remove ? 'Remove sentence' : 'Apply'}
            </Button>
            <Button size="xs" variant="ghost" disabled={busy} onClick={() => (setDraft(remove ? c.sentence : fix.text), setEditing(true))}>
              Edit then apply
            </Button>
            <Button size="xs" variant="ghost" disabled={busy} onClick={onIgnore}>
              Ignore
            </Button>
          </>
        )}
      </div>
    </div>
  )
}

function Claim({ c, fixing }: { c: VerifiedClaim; fixing?: { busy: boolean; open: boolean; toggle: () => void; apply: (replacement: string) => void; ignore: () => void } }) {
  const v = VERDICT[c.verdict] ?? VERDICT.unsupported
  const body = (
    <>
      <ToneBadge tone={v.tone} dot={false} className="shrink-0">
        {v.label}
      </ToneBadge>
      <span className={cn('text-sm', v.blocking ? 'text-fg' : 'text-fg-muted')}>{c.claim}</span>
      {fixing && <WandSparkles className="mt-0.5 size-3.5 shrink-0 text-fg-subtle" aria-label="Has a suggested fix" />}
    </>
  )
  return (
    <li className="space-y-1 py-2">
      {fixing ? (
        <button type="button" className="flex w-full items-start gap-2 rounded text-left hover:bg-surface-hover" aria-expanded={fixing.open} onClick={fixing.toggle}>
          {body}
        </button>
      ) : (
        <div className="flex items-start gap-2">{body}</div>
      )}
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
      {fixing?.open && <FixCard c={c} busy={fixing.busy} onApply={fixing.apply} onIgnore={fixing.ignore} />}
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
  fixTarget,
}: {
  verification: Verification | undefined
  state: VerificationState
  onVerify?: () => void
  verifying?: boolean
  /** What a passed check unlocks, e.g. "approval" or "Copy". */
  gate: string
  compact?: boolean
  /** Where a suggested fix is applied; leave out when the text can't be edited right now. */
  fixTarget?: FixTarget
}) {
  const apply = useApplyClaimFixes()
  const [open, setOpen] = useState<string | null>(null)
  const [ignored, setIgnored] = useState<string[]>([])
  const claims = verification?.claims ?? []
  const fixable = fixTarget ? claims.filter((c) => (VERDICT[c.verdict]?.blocking ?? true) && c.fix && !c.skipped && !ignored.includes(c.sentence)) : []
  const sentences = [...new Set(fixable.map((c) => c.sentence))]
  const run = (fixes: FixItem[]) => {
    if (!fixTarget) return
    apply.mutate(
      { target: fixTarget, fixes },
      {
        onSuccess: (r) => {
          setOpen(null)
          toast.success(r.verification_state === 'passed' ? 'Fix applied: every claim holds' : 'Fix applied: changed sentences re-checked')
        },
        onError: (e) => toast.error(e.message),
      },
    )
  }
  const fixing = (c: VerifiedClaim) =>
    fixTarget && c.fix && !c.skipped && !ignored.includes(c.sentence)
      ? {
          busy: apply.isPending,
          open: open === c.sentence,
          toggle: () => setOpen(open === c.sentence ? null : c.sentence),
          apply: (replacement: string) => run([{ sentence: c.sentence, replacement }]),
          ignore: () => (setIgnored([...ignored, c.sentence]), setOpen(null)),
        }
      : undefined
  const blocking = claims.filter((c) => VERDICT[c.verdict]?.blocking ?? true)
  const garbled = claims.filter((c) => c.verdict === 'garbled')
  const rest = claims.filter((c) => !(VERDICT[c.verdict]?.blocking ?? true) && c.verdict !== 'garbled')
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
          {sentences.length > 1 && (
            <div className="flex items-center gap-2 py-1.5">
              <Button size="xs" variant="secondary" disabled={apply.isPending} onClick={() => run(sentences.map((s) => ({ sentence: s, replacement: fixable.find((c) => c.sentence === s)?.fix?.text ?? '' })))}>
                {apply.isPending ? <LoaderCircle className="animate-spin" /> : <WandSparkles />} Apply all fixes ({sentences.length})
              </Button>
              <span className="text-xs text-fg-subtle">Only the changed sentences are checked again.</span>
            </div>
          )}
          {blocking.length > 0 && <ul className="divide-y divide-border">{blocking.map((c, i) => <Claim key={`b${i}`} c={c} fixing={fixing(c)} />)}</ul>}
          {garbled.length > 0 && (
            <div className="py-1.5">
              <p className="text-xs font-medium text-warning-fg">
                {garbled.length === 1 ? 'A sentence reads badly (a warning, it does not block approval)' : `${garbled.length} sentences read badly (warnings, they do not block approval)`}
              </p>
              <ul className="divide-y divide-border">{garbled.map((c, i) => <Claim key={`g${i}`} c={c} />)}</ul>
            </div>
          )}
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
