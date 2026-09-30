import { ExternalLink, Globe, Plus, RefreshCw, Search, X } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { ToneBadge, type Tone } from '@/components/app/badges'
import { EmptyState, ErrorState } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip } from '@/components/ui/tooltip'
import { relativeTime } from '@/lib/format'
import { useAddSignal, useCompanyResearch, usePatchSignal, useResearchNow, useSetWebsite } from '@/lib/queries/research'
import type { CompanyResearch } from '@/lib/types'
import { cn } from '@/lib/utils'

const KIND: Record<string, { label: string; tone: Tone }> = {
  customer_result: { label: 'Customer result', tone: 'green' },
  technical: { label: 'Technical', tone: 'violet' },
  launch: { label: 'Launch', tone: 'blue' },
  product: { label: 'Product', tone: 'slate' },
  funding: { label: 'Funding', tone: 'amber' },
  expansion: { label: 'Expansion', tone: 'teal' },
  other: { label: 'Other', tone: 'gray' },
}

function RunLine({ data }: { data: CompanyResearch }) {
  const run = data.last_run
  const p = data.progress
  if (p?.status === 'running') {
    const label = p.phase === 'extracting' ? 'Extracting signals' : p.phase === 'fetching' ? 'Fetching pages' : 'Starting'
    return (
      <p className="text-xs text-fg-muted" aria-live="polite">
        {label}
        {p.total ? ` (${p.done}/${p.total})` : ''}…
      </p>
    )
  }
  if (p?.status === 'failed') return <p className="text-xs text-danger-fg">{p.error}</p>
  if (!run) return <p className="text-xs text-fg-subtle">Not researched yet. It runs when you draft an email here, or with Research now.</p>
  const models = [...new Set(run.calls.map((c) => c.model))].join(', ')
  const seconds = run.calls.reduce((n, c) => n + (c.duration_ms ?? 0), 0) / 1000
  const tokens = run.calls.reduce((n, c) => n + (c.prompt_tokens ?? 0) + (c.output_tokens ?? 0), 0)
  return (
    <p className="text-xs text-fg-subtle">
      {run.status === 'failed'
        ? `Last run failed: ${run.error}`
        : `Researched ${relativeTime(run.started_at)} · ${run.pages} pages · ${run.calls.length} model call${run.calls.length === 1 ? '' : 's'}${models ? ` · ${models}` : ''}${seconds ? ` · ${Math.round(seconds)}s` : ''}${tokens ? ` · ${tokens.toLocaleString()} tokens` : ''} · ${run.signals_kept} kept, ${run.signals_dropped} dropped`}
      {data.reused_at && ` · reused by a draft ${relativeTime(data.reused_at)} (no fetch, no model call)`}
    </p>
  )
}

/** A company's verified signals: pick the ones its emails may use, add your own, refresh. */
export function SignalsPanel({ companyId, compact = false }: { companyId: number; compact?: boolean }) {
  const { data, isPending, error, refetch } = useCompanyResearch(companyId)
  const now = useResearchNow()
  const patch = usePatchSignal(companyId)
  const add = useAddSignal(companyId)
  const setSite = useSetWebsite(companyId)
  const [adding, setAdding] = useState(false)
  const [fact, setFact] = useState('')
  const [url, setUrl] = useState('')
  const [kind, setKind] = useState('other')
  const [site, setSiteText] = useState('')

  if (isPending) return <Skeleton className={cn(compact ? 'h-24' : 'm-4 h-24')} />
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />
  const running = data.progress?.status === 'running' || now.isPending
  const research = () =>
    now.mutate({ companyId, force: true }, { onError: (e) => toast.error(e.message) })

  return (
    <div className="space-y-3" data-tour="signals-panel">
      <div className="flex flex-wrap items-center gap-2">
        {data.site ? (
          <a href={data.site} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm text-fg-muted hover:underline">
            <Globe className="size-3.5" />
            {data.site.replace(/^https?:\/\//, '')}
          </a>
        ) : (
          <span className="flex items-center gap-2">
            <Input value={site} onChange={(e) => setSiteText(e.target.value)} placeholder="Company website (e.g. example.com)" className="h-8 w-64" aria-label="Company website" />
            <Button size="sm" disabled={!site.trim() || setSite.isPending} onClick={() => setSite.mutate(site, { onError: (e) => toast.error(e.message) })}>
              Save
            </Button>
          </span>
        )}
        <span className="flex-1" />
        <Tooltip content="Fetches the company's site and recent news, then extracts signals with the model (it costs model calls)">
          <Button size="sm" onClick={research} disabled={running || !data.site}>
            {data.last_run ? <RefreshCw className={running ? 'animate-spin' : undefined} /> : <Search />}
            {running ? 'Researching…' : data.last_run ? 'Refresh signals' : 'Research now'}
          </Button>
        </Tooltip>
        <Button size="sm" variant="ghost" onClick={() => setAdding(!adding)}>
          <Plus />
          Add my own
        </Button>
      </div>
      <RunLine data={data} />
      {adding && (
        <div className="grid grid-cols-[minmax(0,1fr)_14rem_9rem_auto] gap-2 max-lg:grid-cols-1">
          <Input value={fact} onChange={(e) => setFact(e.target.value)} placeholder="A fact about them, in a sentence" aria-label="Signal fact" />
          <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Source link (optional)" aria-label="Signal source" />
          <Select size="sm" value={kind} onValueChange={setKind} options={Object.entries(KIND).map(([value, k]) => ({ value, label: k.label }))} aria-label="Signal kind" />
          <Button
            size="sm"
            disabled={fact.trim().length < 8 || add.isPending}
            onClick={() =>
              add.mutate(
                { fact, source_url: url, kind },
                { onSuccess: () => (setFact(''), setUrl(''), setAdding(false), toast.success('Signal added and selected')), onError: (e) => toast.error(e.message) },
              )
            }
          >
            Add
          </Button>
        </div>
      )}
      {data.signals.length === 0 ? (
        <EmptyState
          compact
          icon={Search}
          title="No signals yet"
          description="Emails open with one or two verified facts about the company. Research it, or add one you know."
          action={<TourButton tour="signals" />}
        />
      ) : (
        <ul className="overflow-hidden rounded-lg border border-border bg-surface">
          {data.signals.map((s) => (
            <li key={s.id} className="flex items-start gap-3 border-b border-border px-3 py-2.5 last:border-b-0">
              <Checkbox
                checked={s.selected}
                onCheckedChange={(v) => patch.mutate({ id: s.id, selected: v === true }, { onError: (e) => toast.error(e.message) })}
                aria-label={s.selected ? 'Used in emails' : 'Not used in emails'}
                className="mt-0.5"
              />
              <div className="min-w-0 flex-1 space-y-1">
                <Tooltip content={s.origin === 'manual' ? 'Added by you' : `“${s.quote}”`}>
                  <p className="text-sm">{s.fact}</p>
                </Tooltip>
                <p className="flex flex-wrap items-center gap-2 text-xs text-fg-subtle">
                  <ToneBadge tone={KIND[s.kind]?.tone ?? 'gray'} dot={false}>
                    {KIND[s.kind]?.label ?? s.kind}
                  </ToneBadge>
                  {s.source_url && (
                    <a href={s.source_url} target="_blank" rel="noreferrer" className="inline-flex max-w-72 items-center gap-1 truncate hover:underline">
                      {s.source_url.replace(/^https?:\/\/(www\.)?/, '')}
                      <ExternalLink className="size-3 shrink-0" />
                    </a>
                  )}
                  {s.page_date && <span>dated {new Date(s.page_date).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })}</span>}
                  <span>fetched {relativeTime(s.fetched_at)}</span>
                  {s.origin === 'manual' && <span>· yours</span>}
                </p>
              </div>
              <Tooltip content="Dismiss (never used)">
                <Button size="icon-sm" variant="ghost" aria-label="Dismiss signal" onClick={() => patch.mutate({ id: s.id, dismissed: true }, { onSuccess: () => toast('Signal dismissed') })}>
                  <X />
                </Button>
              </Tooltip>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
