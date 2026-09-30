import { FileStack, FileText, Mail, ScrollText } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { ToneBadge, type Tone } from '@/components/app/badges'
import { PageHeader } from '@/components/app/PageHeader'
import { EmptyState, ErrorState, SkeletonRows } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Kbd } from '@/components/ui/kbd'
import { Select } from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useListKeyboard } from '@/hooks/useListKeyboard'
import { useSearchParamState } from '@/hooks/useSearchParamState'
import { relativeTime } from '@/lib/format'
import { studioHref, useStudioDocuments } from '@/lib/queries/studio'
import type { StudioDocument, StudioKind } from '@/lib/types'
import { cn } from '@/lib/utils'

const KIND = {
  cv: { label: 'CV', icon: FileText },
  pdf: { label: 'Cover letter', icon: ScrollText },
  form: { label: 'Form text', icon: Mail },
} as const
const STATUS: Record<StudioDocument['status'], { label: string; tone: Tone }> = {
  draft: { label: 'Draft', tone: 'amber' },
  approved: { label: 'Approved', tone: 'green' },
  sent: { label: 'Sent (locked)', tone: 'blue' },
  superseded: { label: 'Superseded', tone: 'gray' },
}

/** Every CV and cover letter across jobs; Enter opens its studio. */
export default function StudioPage() {
  const url = useSearchParamState()
  const navigate = useNavigate()
  const kind = (url.get('type') as StudioKind | null) ?? undefined
  const status = url.get('status') ?? undefined
  const q = url.get('q') ?? ''
  const [search, setSearch] = useState(q)
  const { data, isPending, error, refetch } = useStudioDocuments({ kind, status, q: q || undefined })
  const [selected, setSelected] = useState<string | null>(null)
  const items = data?.items ?? []
  const key = (d: StudioDocument) => `${d.kind}-${d.id}`
  const byKey = (k: string) => items.find((d) => key(d) === k)

  useListKeyboard({
    ids: items.map(key),
    selectedId: selected,
    onSelect: setSelected,
    onOpen: (k) => {
      const d = byKey(k)
      if (d) navigate(studioHref(d))
    },
  })

  const total = data ? data.counts.cv + data.counts.pdf + data.counts.form : 0
  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Studio" description="Every tailored CV and cover letter, across jobs. Open one to review, edit or approve it." />
      <div data-tour="studio-filters" className="flex flex-wrap items-center gap-4 border-b border-border px-6">
        <Tabs value={kind ?? 'all'} onValueChange={(v) => url.set({ type: v === 'all' ? null : v })}>
          <TabsList>
            <TabsTrigger value="all" count={data ? total : undefined}>
              All
            </TabsTrigger>
            <TabsTrigger value="cv" count={data?.counts.cv}>
              CVs
            </TabsTrigger>
            <TabsTrigger value="pdf" count={data?.counts.pdf}>
              Cover letters
            </TabsTrigger>
            <TabsTrigger value="form" count={data?.counts.form}>
              Form texts
            </TabsTrigger>
          </TabsList>
        </Tabs>
        <span className="flex-1" />
        <Select
          size="sm"
          aria-label="Status"
          value={status ?? 'all'}
          onValueChange={(v) => url.set({ status: v === 'all' ? null : v })}
          options={[
            { value: 'all', label: 'Any status' },
            { value: 'draft', label: 'Drafts' },
            { value: 'approved', label: 'Approved' },
            { value: 'sent', label: 'Sent (locked)' },
            { value: 'superseded', label: 'Superseded' },
          ]}
          className="w-40"
        />
        <Input
          value={search}
          placeholder="Filter by job or company"
          aria-label="Filter by job or company"
          className="h-8 w-56"
          onChange={(e) => {
            setSearch(e.target.value)
            url.set({ q: e.target.value || null })
          }}
        />
      </div>
      {isPending ? (
        <SkeletonRows rows={6} />
      ) : error ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={FileStack}
          title={kind || status || q ? 'Nothing matches these filters' : 'No CVs or letters yet'}
          description={
            kind || status || q
              ? 'Clear a filter to see more.'
              : 'Tailored CVs and cover letters appear here once you generate them from a job (Shortlist → Generate CV).'
          }
          action={
            <div className="flex gap-2">
              {kind || status || q ? (
                <Button variant="default" onClick={() => (setSearch(''), url.set({ type: null, status: null, q: null }))}>
                  Clear filters
                </Button>
              ) : (
                <Button variant="default" asChild>
                  <Link to="/pipeline">Open Pipeline</Link>
                </Button>
              )}
              <TourButton tour="studio" />
            </div>
          }
        />
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto" data-tour="studio-list">
          <p className="border-b border-border bg-bg-subtle px-6 py-2 text-xs text-fg-subtle">
            <Kbd>J</Kbd> <Kbd>K</Kbd> move · <Kbd>Enter</Kbd> open in its studio
          </p>
          <div role="listbox" aria-label="Documents">
            {items.map((d) => {
              const Icon = KIND[d.kind].icon
              return (
                <Link
                  key={key(d)}
                  to={studioHref(d)}
                  data-row-id={key(d)}
                  role="option"
                  aria-selected={selected === key(d)}
                  onMouseEnter={() => setSelected(key(d))}
                  className={cn(
                    'relative flex items-center gap-3 border-b border-border px-6 py-2.5 transition-colors duration-120',
                    selected === key(d) ? 'bg-surface-selected' : 'hover:bg-surface-hover',
                  )}
                >
                  {selected === key(d) && <span className="absolute inset-y-0 left-0 w-0.5 bg-primary" />}
                  <Icon className="size-4 shrink-0 text-fg-subtle" />
                  <span className="w-24 shrink-0 text-xs text-fg-muted">
                    {KIND[d.kind].label} v{d.version}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{d.job_title}</span>
                    <span className="block truncate text-xs text-fg-muted">
                      {d.company_name} · {d.detail}
                      {d.language ? ` · ${d.language.toUpperCase()}` : ''}
                    </span>
                  </span>
                  {d.problems > 0 && d.status === 'draft' && (
                    <ToneBadge tone="red" dot={false}>
                      {d.problems} to fix
                    </ToneBadge>
                  )}
                  <ToneBadge tone={STATUS[d.status].tone}>{STATUS[d.status].label}</ToneBadge>
                  <span className="w-20 shrink-0 text-right text-xs text-fg-subtle">{relativeTime(d.updated_at)}</span>
                </Link>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
