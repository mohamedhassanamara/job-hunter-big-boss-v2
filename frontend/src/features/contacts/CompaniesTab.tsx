import { Building2, Copy, ExternalLink, Search, SearchX, UserRoundCheck, Users } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { StageDot, ToneBadge } from '@/components/app/badges'
import { EmptyState, ErrorState, SkeletonRows } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip } from '@/components/ui/tooltip'
import { useListKeyboard } from '@/hooks/useListKeyboard'
import { useSearchParamState } from '@/hooks/useSearchParamState'
import { initials, pluralize, relativeTime } from '@/lib/format'
import { useCompanies, useCompany } from '@/lib/queries/library'
import type { Contact } from '@/lib/types'
import { cn } from '@/lib/utils'

const SOURCE: Record<Contact['source'], { label: string; tone: 'green' | 'blue' | 'gray' }> = {
  apollo_dump: { label: 'Apollo import', tone: 'green' },
  apollo_lookup: { label: 'Apollo lookup', tone: 'blue' },
  manual: { label: 'Manual', tone: 'gray' },
}

function CompanyDetailPane({ id }: { id: number }) {
  const { data, isPending, error, refetch } = useCompany(id)
  if (isPending)
    return (
      <div className="space-y-3 p-6">
        <Skeleton className="h-6 w-56" />
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-40" />
      </div>
    )
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />

  const copy = (email: string) => {
    void navigator.clipboard.writeText(email)
    toast.success('Email copied')
  }

  return (
    <div className="space-y-5 p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">{data.name}</h2>
          <div className="mt-1 flex items-center gap-2 text-sm text-fg-muted">
            {data.website && (
              <a href={data.website} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-fg">
                {data.domain}
                <ExternalLink className="size-3.5" />
              </a>
            )}
            {data.contacted_at ? (
              <ToneBadge tone="amber">Contacted {relativeTime(data.contacted_at)}</ToneBadge>
            ) : (
              <ToneBadge tone="gray">Not contacted</ToneBadge>
            )}
          </div>
        </div>
      </div>

      {data.jobs.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-medium text-fg-subtle">Jobs at {data.name}</p>
          <div className="flex flex-wrap gap-2">
            {data.jobs.map((j) => (
              <Link
                key={j.id}
                to={`/jobs/${j.id}`}
                className="inline-flex items-center gap-2 rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm hover:border-border-strong"
              >
                <StageDot stage={j.stage} />
                {j.title}
                <span className="text-xs text-fg-subtle">{j.stage_label}</span>
              </Link>
            ))}
          </div>
        </div>
      )}

      <div>
        <p className="mb-2 text-xs font-medium text-fg-subtle">{pluralize(data.contacts.length, 'contact')}</p>
        {data.contacts.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border-strong p-6 text-center text-sm text-fg-muted">
            No contacts at this company. Jobs here go to web apply unless a lookup finds someone.
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-border bg-surface">
            {data.contacts.map((c) => (
              <div key={c.id} className="flex items-center gap-3 border-b border-border px-4 py-2.5 last:border-b-0">
                <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary-subtle text-xs font-semibold text-primary">
                  {initials(c.full_name)}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{c.full_name}</p>
                  <p className="truncate text-xs text-fg-muted">{c.title}</p>
                </div>
                {c.email && (
                  <Button size="xs" variant="ghost" onClick={() => copy(c.email!)} className="max-w-64">
                    <span className="truncate">{c.email}</span>
                    <Copy className="text-fg-subtle" />
                  </Button>
                )}
                <ToneBadge tone={SOURCE[c.source].tone} dot={false}>
                  {SOURCE[c.source].label}
                </ToneBadge>
                {c.linkedin_url && (
                  <Tooltip content="LinkedIn profile">
                    <Button size="icon-sm" variant="ghost" asChild>
                      <a href={c.linkedin_url} target="_blank" rel="noreferrer" aria-label="LinkedIn profile">
                        <ExternalLink />
                      </a>
                    </Button>
                  </Tooltip>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export function CompaniesTab({ onImport }: { onImport: () => void }) {
  const url = useSearchParamState()
  const [q, setQ] = useState('')
  const { data, isPending, error, refetch } = useCompanies(q)
  const selected = url.get('company') ? Number(url.get('company')) : null
  const companies = useMemo(() => data ?? [], [data])
  const ids = useMemo(() => companies.map((c) => c.id), [companies])

  useEffect(() => {
    const first = companies.find((c) => c.contact_count > 0) ?? companies[0]
    if (selected === null && first && !q) url.set({ company: first.id })
  }, [selected, companies, q, url])

  useListKeyboard({ ids, selectedId: selected, onSelect: (id) => url.set({ company: id }) })

  const totalContacts = companies.reduce((n, c) => n + c.contact_count, 0)

  if (!isPending && !error && companies.length === 0 && !q) {
    return (
      <EmptyState
        icon={Users}
        title="No contacts yet"
        description="Import your Apollo export so jobs can be matched to a person automatically."
        action={
          <div className="flex gap-2">
            <Button variant="default" size="sm" onClick={onImport}>
              Import CSV
            </Button>
            <TourButton tour="contacts" />
          </div>
        }
      />
    )
  }

  return (
    <div className="flex h-full min-h-0">
      <div data-tour="contacts-companies" className="flex w-[340px] shrink-0 flex-col border-r border-border bg-bg">
        <div className="space-y-2 border-b border-border p-3">
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-fg-subtle" />
            <Input
              data-page-search
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === 'Escape' && e.currentTarget.blur()}
              placeholder="Search companies"
              className="h-7 pl-8"
            />
          </div>
          <p className="px-0.5 text-2xs text-fg-subtle">
            {pluralize(companies.length, 'company', 'companies')} · {pluralize(totalContacts, 'contact')}
          </p>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {isPending ? (
            <SkeletonRows rows={8} />
          ) : error ? (
            <ErrorState compact error={error} onRetry={() => refetch()} />
          ) : companies.length === 0 ? (
            <EmptyState compact icon={SearchX} title={`No companies match “${q}”`} />
          ) : (
            companies.map((c) => (
              <button
                key={c.id}
                data-row-id={c.id}
                onClick={() => url.set({ company: c.id })}
                className={cn(
                  'relative flex w-full items-center gap-3 border-b border-border px-4 py-2.5 text-left transition-colors duration-120',
                  selected === c.id ? 'bg-surface-selected' : 'hover:bg-surface-hover',
                )}
              >
                {selected === c.id && <span className="absolute inset-y-0 left-0 w-0.5 bg-primary" />}
                <Building2 className="size-4 shrink-0 text-fg-subtle" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{c.name}</p>
                  <p className="truncate text-xs text-fg-muted">
                    {pluralize(c.contact_count, 'contact')}
                    {c.open_jobs > 0 && ` · ${pluralize(c.open_jobs, 'open job')}`}
                  </p>
                </div>
                {c.contacted_at && (
                  <Tooltip content={`Contacted ${relativeTime(c.contacted_at)}`}>
                    <UserRoundCheck className="size-4 text-warning-dot" />
                  </Tooltip>
                )}
              </button>
            ))
          )}
        </div>
      </div>
      <div data-tour="contacts-detail" className="min-w-0 flex-1 overflow-y-auto">
        {selected !== null ? (
          <CompanyDetailPane key={selected} id={selected} />
        ) : (
          <EmptyState icon={Building2} title="Select a company" description="Contacts and jobs for the company appear here." />
        )}
      </div>
    </div>
  )
}
