import { RefreshCw, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ErrorState } from '@/components/app/states'
import { Skeleton } from '@/components/ui/skeleton'
import { useSaveSetting } from '@/lib/queries/library'
import { useEnableKey, useProviders, useSyncProviders } from '@/lib/queries/providers'
import type { ProviderKey, SettingsView } from '@/lib/types'
import { cn } from '@/lib/utils'
import { Card, Field, SaveBar } from './sections'

const NAMES: Record<string, string> = { hunter: 'Hunter', prospeo: 'Prospeo', apollo: 'Apollo', apify: 'Apify' }
const fmt = (k: ProviderKey, n: number) => (k.unit === 'usd' ? `$${n.toFixed(2)}` : `${Math.round(n * 10) / 10}`)

/** Credits left per key (and Apify spend) this month, the cache age, and the call log. */
export function ProvidersCard({ settings }: { settings: SettingsView }) {
  const status = useProviders()
  const sync = useSyncProviders()
  const enable = useEnableKey()
  const save = useSaveSetting()
  const saved = settings.values.providers ?? {}
  const initialAge = Number(saved.max_age_days ?? 90)
  const [age, setAge] = useState(initialAge)
  const apolloLimit = Number((saved.limits as Record<string, number> | undefined)?.apollo ?? 50)
  const [apollo, setApollo] = useState(apolloLimit)
  const dirty = age !== initialAge || apollo !== apolloLimit

  const onSave = async () => {
    if (!Number.isInteger(age) || age < 1 || age > 730) return toast.error('The cache age is between 1 and 730 days')
    if (!Number.isFinite(apollo) || apollo < 0) return toast.error('The Apollo limit is a number of credits')
    try {
      await save.mutateAsync({ key: 'providers', value: { ...saved, max_age_days: age, limits: { ...(saved.limits as object | undefined), apollo } } })
      toast.success('Provider settings saved')
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  return (
    <Card
      title="Contact providers"
      description="The Find contact button looks in the company cache first, then Hunter, Prospeo, Apollo and Apify, and stops at the first verified email. Credits are counted per key and reset each month; a key is never used past its credits, and a key a provider refuses is disabled."
      footer={<SaveBar dirty={dirty} saving={save.isPending} onReset={() => (setAge(initialAge), setApollo(apolloLimit))} onSave={() => void onSave()} />}
    >
      <div data-tour="settings-providers" className="space-y-3">
        {status.isPending ? (
          <Skeleton className="h-40" />
        ) : status.error ? (
          <ErrorState error={status.error} onRetry={() => void status.refetch()} compact />
        ) : status.data.keys.length === 0 ? (
          <p className="text-sm text-fg-muted">No provider key yet: add HUNTER_API_KEYS, PROSPEO_API_KEYS, APOLLO_API_KEYS or APIFY_TOKEN to .env and restart.</p>
        ) : (
          <>
            {status.data.warnings.map((w) => (
              <p key={w} className="flex items-center gap-2 rounded-md bg-warning-bg px-3 py-2 text-xs text-warning-fg">
                <TriangleAlert className="size-3.5" />
                {w}
              </p>
            ))}
            <div className="overflow-hidden rounded-lg border border-border bg-surface">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs text-fg-subtle">
                    <th className="px-3 py-2 font-medium">Key</th>
                    <th className="px-3 py-2 font-medium">Left this month</th>
                    <th className="px-3 py-2 font-medium">Used</th>
                    <th className="px-3 py-2 font-medium">Calls</th>
                    <th className="px-3 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {status.data.keys.map((k) => (
                    <tr key={k.label} className="border-b border-border last:border-b-0">
                      <td className="px-3 py-1.5">
                        <span className="font-medium">{NAMES[k.provider]}</span> <span className="text-fg-subtle">{k.label.split('#')[1] ? `key ${k.label.split('#')[1]}` : ''}</span>
                      </td>
                      <td className={cn('px-3 py-1.5 tabular-nums', k.disabled || k.remaining <= 0 ? 'text-danger-fg' : k.remaining / (k.limit || 1) < 0.2 ? 'text-warning-fg' : '')}>
                        {fmt(k, k.remaining)} / {fmt(k, k.limit)} {k.unit === 'usd' ? '' : 'credits'}
                      </td>
                      <td className="px-3 py-1.5 text-fg-muted tabular-nums">{fmt(k, k.used)}</td>
                      <td className="px-3 py-1.5 text-fg-muted tabular-nums">{k.calls}</td>
                      <td className="px-3 py-1.5 text-right">
                        {k.disabled && (
                          <Button size="xs" variant="outline" disabled={enable.isPending} onClick={() => enable.mutate({ provider: k.provider, label: k.label })}>
                            Enable again
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex items-center gap-2 text-xs text-fg-subtle">
              <Button size="sm" variant="outline" disabled={sync.isPending} onClick={() => sync.mutate(undefined, { onError: (e) => toast.error(e.message) })}>
                <RefreshCw className={cn(sync.isPending && 'animate-spin')} />
                Sync with the providers
              </Button>
              Reads the real balance from Hunter, Prospeo and Apify (free). Apollo has no balance endpoint on free plans: its credits are counted here. Apify spend this month: ${status.data.spend_usd.toFixed(3)}.
            </div>
            {status.data.recent_calls.length > 0 && (
              <details className="text-xs text-fg-muted">
                <summary className="cursor-pointer text-fg-subtle">Last {status.data.recent_calls.length} calls</summary>
                <ul className="mt-1.5 space-y-0.5 tabular-nums">
                  {status.data.recent_calls.map((c, i) => (
                    <li key={i} className={cn(!c.ok && 'text-danger-fg')}>
                      {new Date(c.created_at).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })} · {c.key_label ?? c.provider} · {c.endpoint}
                      {c.credits ? ` · ${c.credits} credits` : ''}
                      {c.cost_usd ? ` · $${c.cost_usd.toFixed(3)}` : ''} · {c.ok ? 'ok' : c.result}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </>
        )}
      </div>
      <Field label="Company cache lasts" hint="A company looked up less than this long ago is never queried again unless you ask">
        <div className="flex items-center gap-2 text-sm">
          <Input type="number" min={1} max={730} value={age} onChange={(e) => setAge(Number(e.target.value))} className="w-24" aria-label="Company cache lasts (days)" />
          days
        </div>
      </Field>
      <Field label="Apollo monthly credits" hint="Counted here: Apollo can't tell us. The waterfall stops using Apollo past this">
        <Input type="number" min={0} value={apollo} onChange={(e) => setApollo(Number(e.target.value))} className="w-24" aria-label="Apollo monthly credits" />
      </Field>
    </Card>
  )
}
