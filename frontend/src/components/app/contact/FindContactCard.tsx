import { ArrowRight, CircleCheck, CircleDashed, CircleX, RefreshCw, Sparkles, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { ToneBadge, type Tone } from '@/components/app/badges'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useFindContact, useUseFoundContact } from '@/lib/queries/getContact'
import type { FindContactResult, WaterfallCandidate, WaterfallStep } from '@/lib/types'
import { cn } from '@/lib/utils'

const PROVIDER: Record<string, string> = { cache: 'Cache', hunter: 'Hunter', prospeo: 'Prospeo', apollo: 'Apollo', apify: 'Apify', pattern: 'Email pattern', manual: 'Apollo extension' }

const STEP_TONE: Record<string, Tone> = { found: 'green', empty: 'gray', cached: 'blue', skipped: 'gray', no_key: 'amber', exhausted: 'amber', rate_limited: 'amber', error: 'red' }
const STEP_LABEL: Record<string, string> = { found: 'found', empty: 'nobody', cached: 'already queried', skipped: 'skipped', no_key: 'no key', exhausted: 'no credits', rate_limited: 'rate limited', error: 'error' }

const spent = (c: number, usd: number) => [c ? `${c} credit${c === 1 ? '' : 's'}` : '', usd ? `$${usd.toFixed(3)}` : ''].filter(Boolean).join(' · ') || '0 credits'

function Step({ s }: { s: WaterfallStep }) {
  const Icon = s.status === 'found' ? CircleCheck : s.status === 'error' || s.status === 'no_key' || s.status === 'exhausted' ? CircleX : CircleDashed
  return (
    <li className="flex items-start gap-2 text-xs">
      <Icon className={cn('mt-0.5 size-3.5 shrink-0', s.status === 'found' ? 'text-success-fg' : 'text-fg-subtle')} />
      <span className="w-28 shrink-0 font-medium">
        {PROVIDER[s.provider]}
        {s.key_label && <span className="font-normal text-fg-subtle"> {s.key_label.split('#')[1] ? `key ${s.key_label.split('#')[1]}` : ''}</span>}
      </span>
      <ToneBadge tone={STEP_TONE[s.status] ?? 'gray'} dot={false}>
        {STEP_LABEL[s.status] ?? s.status}
      </ToneBadge>
      <span className="min-w-0 flex-1 text-fg-muted">
        {s.detail}
        {(s.credits > 0 || s.usd > 0) && <span className="text-fg-subtle"> · {spent(s.credits, s.usd)}</span>}
      </span>
    </li>
  )
}

function Candidate({ c, appId, onUsed, current }: { c: WaterfallCandidate; appId: number; onUsed?: () => void; current: boolean }) {
  const use = useUseFoundContact()
  const source = [PROVIDER[c.provider] ?? c.provider, c.actor, c.key_label].filter(Boolean).join(' · ')
  return (
    <li className="flex items-start gap-3 rounded-lg border border-border bg-surface px-3.5 py-2.5" data-tour="find-candidate">
      <div className="min-w-0 flex-1 space-y-0.5">
        <p className="text-sm font-medium">
          {c.full_name}
          {c.title && <span className="font-normal text-fg-muted"> · {c.title}</span>}
        </p>
        <p className="text-xs text-fg-muted">{c.email ?? 'No email revealed'}</p>
        <p className="flex flex-wrap items-center gap-x-2 text-xs text-fg-subtle">
          {c.rank_label && <span>{c.rank_label}</span>}
          <span>via {source}</span>
          <ToneBadge tone={c.verified ? 'green' : c.email_status === 'accept_all' ? 'amber' : 'gray'} dot={false}>
            {c.verified ? 'verified email' : c.email_status === 'accept_all' ? 'catch-all: not used' : c.email ? 'unverified: not used' : 'not revealed'}
          </ToneBadge>
          {c.note && !c.verified && <span>{c.note}</span>}
          {current && <ToneBadge tone="blue" dot={false}>current contact</ToneBadge>}
        </p>
        {c.alerts.map((a) => (
          <p key={a} className="flex items-center gap-1 text-xs text-warning-fg">
            <TriangleAlert className="size-3.5" />
            May have left: {a}
          </p>
        ))}
      </div>
      {c.verified && c.contact_id !== null && !current && (
        <Button
          size="sm"
          variant="outline"
          disabled={use.isPending}
          onClick={() =>
            use.mutate(
              { appId, contactId: c.contact_id! },
              { onSuccess: () => (toast.success(`Writing to ${c.full_name}: verify them next`), onUsed?.()), onError: (e) => toast.error(e.message) },
            )
          }
        >
          Use
          <ArrowRight />
        </Button>
      )}
    </li>
  )
}

/** One click: the cache, then Hunter, Prospeo, Apollo, Apify and the email pattern, stopping at
 * the first verified email. Shows the steps with their cost and the top 3 by your ranking. */
export function FindContactCard({ appId, domain, onUsed, quiet = false, currentContactId = null }: { appId: number; domain: string | null; onUsed?: () => void; quiet?: boolean; currentContactId?: number | null }) {
  const find = useFindContact()
  const [typed, setTyped] = useState('')
  const [changing, setChanging] = useState(false)
  const [result, setResult] = useState<FindContactResult | null>(null)
  const run = (requery: boolean) =>
    find.mutate(
      { appId, requery, domain: typed.trim() || undefined },
      {
        onSuccess: (r) => {
          setResult(r)
          if (r.from_cache) toast.success('Already known: 0 credits spent')
          else if (r.found_by) toast.success(`Found with ${PROVIDER[r.found_by]}`, { description: spent(r.credits, r.usd) })
        },
        onError: (e) => toast.error(e.message),
      },
    )
  const needsDomain = result !== null && result.domain === null
  return (
    <div className="space-y-3" data-tour="find-contact">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant={quiet ? 'outline' : 'default'} onClick={() => run(false)} disabled={find.isPending}>
          <Sparkles />
          {find.isPending ? 'Looking…' : result ? 'Find again' : 'Find contact'}
        </Button>
        {result && result.domain && !result.from_cache && (
          <Button size="sm" variant="ghost" onClick={() => run(true)} disabled={find.isPending}>
            <RefreshCw />
            Ask the providers again
          </Button>
        )}
        {result?.domain && result.from_cache && (
          <Button size="sm" variant="ghost" onClick={() => run(true)} disabled={find.isPending}>
            <RefreshCw />
            Re-query this company
          </Button>
        )}
        <span className="text-xs text-fg-subtle">{domain ? `at ${domain}` : 'Cache first, then your providers, stopping at the first verified email.'}</span>
        {domain && (
          <Button size="xs" variant="ghost" onClick={() => setChanging((c) => !c)}>
            Not the right domain?
          </Button>
        )}
      </div>
      {(needsDomain || changing || (!domain && result === null)) && (
        <Input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Company domain, if it isn't found (e.g. acme.com)" aria-label="Company domain" className="max-w-sm" />
      )}
      {result && (
        <div className="space-y-3">
          <ol className="space-y-1.5">
            {result.steps.map((s, i) => (
              <Step key={`${s.provider}-${i}`} s={s} />
            ))}
          </ol>
          <p className="text-xs text-fg-subtle">
            This click: {spent(result.credits, result.usd)}
            {result.domain && ` · ${result.domain}${result.domain_source ? ` (${result.domain_source})` : ''}`}
          </p>
          {result.candidates.length > 0 ? (
            <ul className="space-y-2">
              {result.candidates.map((c, i) => (
                <Candidate key={`${c.full_name}-${i}`} c={c} appId={appId} onUsed={onUsed} current={currentContactId !== null && c.contact_id === currentContactId} />
              ))}
            </ul>
          ) : (
            <p className="text-xs text-warning-fg">Nobody verified: use the Apollo extension below (paste what it shows).</p>
          )}
        </div>
      )}
    </div>
  )
}
