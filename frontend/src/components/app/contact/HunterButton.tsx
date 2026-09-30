import { MailSearch, ShieldCheck } from 'lucide-react'
import { toast } from 'sonner'
import { ToneBadge } from '@/components/app/badges'
import { Button } from '@/components/ui/button'
import { Tooltip } from '@/components/ui/tooltip'
import { useHunterCredits, useHunterFind, useHunterVerify } from '@/lib/queries/getContact'
import type { HunterFound, HunterVerified } from '@/lib/types'

/** Try Hunter: one email search (1 credit), only when you click. Shows what's left first. */
export function HunterFindButton({ appId, fullName, onFound }: { appId: number; fullName: string; onFound: (r: HunterFound) => void }) {
  const credits = useHunterCredits()
  const find = useHunterFind()
  const c = credits.data
  const parts = fullName.trim().split(/\s+/)
  const nameOk = parts.length >= 2 && parts[parts.length - 1].replace('.', '').length >= 2
  const blocked = !c?.configured ? (c?.error ?? 'Add HUNTER_API_KEY to .env to use Hunter') : c.searches_left === 0 ? 'No Hunter searches left this month' : !nameOk ? 'Type their first and last name first' : null
  const left = c?.configured && c.searches_left != null ? ` · ${c.searches_left} of ${c.searches_available} left` : ''
  return (
    <Tooltip content={blocked ?? 'Search Hunter for their email at this company (uses 1 search). Nothing is saved until you save.'}>
      <span>
        <Button
          size="sm"
          variant="ghost"
          disabled={!!blocked || find.isPending}
          data-tour="hunter-button"
          onClick={() =>
            find.mutate(
              { appId, fullName },
              {
                onSuccess: (r) => {
                  if (r.email) {
                    onFound(r)
                    toast.success(`Hunter found ${r.email}`, { description: `Confidence ${r.score ?? '?'} · check it, then save` })
                  } else toast('Hunter found no email for them', { description: `${r.credits.searches_left ?? '?'} searches left` })
                },
                onError: (e) => toast.error(e.message),
              },
            )
          }
        >
          <MailSearch />
          {find.isPending ? 'Asking Hunter…' : `Try Hunter${left}`}
        </Button>
      </span>
    </Tooltip>
  )
}

const RESULT_TONE = { deliverable: 'green', risky: 'amber', undeliverable: 'red', unknown: 'gray' } as const

/** Verify an email that looks wrong with Hunter (1 verification). */
export function HunterVerifyButton({ email, result, onResult }: { email: string; result: HunterVerified | null; onResult: (r: HunterVerified) => void }) {
  const credits = useHunterCredits()
  const verify = useHunterVerify()
  const c = credits.data
  if (result && result.email === email) {
    return (
      <ToneBadge tone={RESULT_TONE[result.result] ?? 'gray'} dot={false}>
        Hunter: {result.result}
      </ToneBadge>
    )
  }
  const blocked = !c?.configured ? 'Add HUNTER_API_KEY to .env to use Hunter' : c.verifications_left === 0 ? 'No Hunter verifications left this month' : !email.includes('@') ? 'Type an email first' : null
  return (
    <Tooltip content={blocked ?? `Check this email with Hunter (1 verification${c?.verifications_left != null ? `, ${c.verifications_left} left` : ''})`}>
      <span>
        <Button
          size="xs"
          variant="ghost"
          disabled={!!blocked || verify.isPending}
          onClick={() => verify.mutate(email, { onSuccess: onResult, onError: (e) => toast.error(e.message) })}
        >
          <ShieldCheck />
          {verify.isPending ? 'Checking…' : 'Verify with Hunter'}
        </Button>
      </span>
    </Tooltip>
  )
}
