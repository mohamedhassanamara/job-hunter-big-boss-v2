import { Building2, Copy, ExternalLink, Search, SearchX, UserPlus, UserRoundCheck, Users } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { ContactTierBadge, FitBadge, StageDot, ToneBadge } from '@/components/app/badges'
import { EmptyState, ErrorState, SkeletonRows } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { SegmentedList, SegmentedTrigger, Tabs } from '@/components/ui/tabs'
import { Tooltip } from '@/components/ui/tooltip'
import { useListKeyboard } from '@/hooks/useListKeyboard'
import { useSearchParamState } from '@/hooks/useSearchParamState'
import { ApiError } from '@/lib/api'
import { initials, pluralize, relativeTime } from '@/lib/format'
import {
  useAddCompanyContact,
  useClearJobContact,
  useCompanies,
  useCompany,
  useSetCompanySize,
  useSetJobContact,
} from '@/lib/queries/library'
import type { CompanyDetail, CompanyFilter, Contact } from '@/lib/types'
import { cn } from '@/lib/utils'
import { SignalsPanel } from '@/components/app/research/SignalsPanel'
import { useContactSearch } from '@/lib/queries/getContact'
import { NewContactDialog } from '@/components/app/NewContactDialog'

const SOURCE: Record<Contact['source'], { label: string; tone: 'green' | 'blue' | 'gray' }> = {
  apollo_dump: { label: 'Apollo import', tone: 'green' },
  found: { label: 'Found by you', tone: 'blue' },
  hunter: { label: 'Hunter', tone: 'blue' },
  manual: { label: 'Manual', tone: 'gray' },
}

const FILTERS: { value: CompanyFilter; label: string }[] = [
  { value: 'with_jobs', label: 'With jobs' },
  { value: 'has_contacts', label: 'Has contacts' },
  { value: 'to_get', label: 'Contact to get' },
  { value: 'no_contact', label: 'No contact' },
]

const AUTO = 'auto'

function JobsTable({ data }: { data: CompanyDetail }) {
  const setContact = useSetJobContact()
  const clear = useClearJobContact()
  if (data.jobs.length === 0) return null
  const options = [
    { value: AUTO, label: 'Automatic (best ranked)' },
    ...data.contacts.map((c) => ({ value: String(c.id), label: `${c.full_name}${c.role_label ? ` · ${c.role_label}` : ''}` })),
  ]
  const pick = (appId: number, value: string) =>
    value === AUTO
      ? clear.mutate(appId, { onSuccess: () => toast.success('Back to automatic matching'), onError: (e) => toast.error(e.message) })
      : setContact.mutate(
          { appId, contactId: Number(value) },
          { onSuccess: () => toast.success('Contact set for this job'), onError: (e) => toast.error(e.message) },
        )
  return (
    <div>
      <p className="mb-2 text-xs font-medium text-fg-subtle">Jobs at {data.name}</p>
      <div className="overflow-hidden rounded-lg border border-border bg-surface">
        {data.jobs.map((j) => (
          <div key={j.application_id} className="flex items-center gap-3 border-b border-border px-4 py-2.5 last:border-b-0">
            <FitBadge fit={j.fit} />
            <Link to={`/jobs/${j.job_id}`} className="min-w-0 flex-1 hover:underline">
              <p className="truncate text-sm font-medium">{j.title}</p>
              <p className="flex items-center gap-1.5 text-xs text-fg-muted">
                <StageDot stage={j.stage} />
                {j.stage_label}
              </p>
            </Link>
            <ContactTierBadge tier={j.contact_tier} />
            {data.contacts.length > 0 && j.stage !== 'closed' && j.stage !== 'done' && j.stage !== 'interview' && (
              <Select
                size="sm"
                aria-label={`Contact for ${j.title}`}
                value={j.contact_id ? String(j.contact_id) : AUTO}
                onValueChange={(v) => pick(j.application_id, v)}
                options={options}
                className="w-60 [&>span]:truncate"
              />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function SizeEditor({ data }: { data: CompanyDetail }) {
  const set = useSetCompanySize()
  const [kind, setKind] = useState<'unknown' | 'max' | 'exact'>(data.employees !== null ? 'exact' : data.employees_max !== null ? 'max' : 'unknown')
  const [value, setValue] = useState(String(data.employees ?? data.employees_max ?? ''))
  const [editing, setEditing] = useState(false)
  if (!editing)
    return (
      <Tooltip content={data.small ? 'Small company: CTO and founders are written to first' : 'Large or unknown size: HR/Talent and engineering managers first'}>
        <button onClick={() => setEditing(true)} className="inline-flex">
          <ToneBadge tone={data.small ? 'teal' : 'gray'}>
            {data.size_label}
            {data.size_source === 'apollo_list' && ' (Apollo list)'}
          </ToneBadge>
        </button>
      </Tooltip>
    )
  const n = Number(value)
  const save = () =>
    set.mutate(
      {
        companyId: data.id,
        employees: kind === 'exact' ? n : null,
        employees_max: kind === 'max' ? n : null,
      },
      {
        onSuccess: (d) => {
          toast.success('Company size saved', { description: `${d.size_label}: jobs here re-matched` })
          setEditing(false)
        },
        onError: (e) => toast.error(e.message),
      },
    )
  return (
    <span className="inline-flex items-center gap-1.5">
      <Select
        size="sm"
        aria-label="Size"
        value={kind}
        onValueChange={(v) => setKind(v as typeof kind)}
        options={[
          { value: 'unknown', label: 'Size unknown' },
          { value: 'max', label: 'Under' },
          { value: 'exact', label: 'Exactly' },
        ]}
        className="w-32"
      />
      {kind !== 'unknown' && (
        <Input type="number" min={1} value={value} onChange={(e) => setValue(e.target.value)} className="h-7 w-24" aria-label="Employees" />
      )}
      {kind !== 'unknown' && <span className="text-xs">employees</span>}
      <Button size="xs" variant="default" disabled={set.isPending || (kind !== 'unknown' && !(n > 0))} onClick={save}>
        Save
      </Button>
      <Button size="xs" variant="ghost" onClick={() => setEditing(false)}>
        Cancel
      </Button>
    </span>
  )
}

function CompanyDetailPane({ id, onMissing }: { id: number; onMissing: () => void }) {
  const { data, isPending, error, refetch } = useCompany(id)
  const add = useAddCompanyContact()
  const search = useContactSearch()
  const [adding, setAdding] = useState(false)
  const missing = error instanceof ApiError && error.status === 404
  // A stale ?company= (another workspace, a removed company): fall back to the list's first.
  useEffect(() => {
    if (missing) onMissing()
  }, [missing, onMissing])
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
            {data.domain && (
              <a href={data.website ?? `https://${data.domain}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-fg">
                {data.domain}
                <ExternalLink className="size-3.5" />
              </a>
            )}
            {data.contacted_at ? (
              <ToneBadge tone="amber">Contacted {relativeTime(data.contacted_at)}</ToneBadge>
            ) : (
              <ToneBadge tone="gray">Not contacted</ToneBadge>
            )}
            <SizeEditor key={`${data.employees}-${data.employees_max}`} data={data} />
            {data.contact_search === 'not_found' && <ToneBadge tone="gray">Nobody found</ToneBadge>}
            {data.contact_search === 'never' && <ToneBadge tone="gray">Never looked up (job board)</ToneBadge>}
            {data.contact_search !== 'none' && (
              <Button
                size="xs"
                variant="ghost"
                onClick={() =>
                  search.mutate(
                    { companyId: data.id, status: 'none' },
                    { onSuccess: () => toast.success('Its jobs are back in Get contact'), onError: (e) => toast.error(e.message) },
                  )
                }
              >
                Look up again
              </Button>
            )}
          </div>
        </div>
        <Button size="sm" onClick={() => setAdding(true)}>
          <UserPlus />
          Add contact
        </Button>
      </div>

      <JobsTable data={data} />

      <div>
        <p className="mb-2 text-xs font-medium text-fg-subtle">
          {pluralize(data.contacts.length, 'contact')} · most relevant first for a {data.small ? 'small' : 'large or unknown-size'} company (Settings → Contacts)
        </p>
        {data.contacts.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border-strong p-6 text-center text-sm text-fg-muted">
            No contacts at this company. Once you shortlist one of its jobs, it joins Outreach → Contacts to get; if you find nobody there, its jobs go to web apply.
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-border bg-surface">
            {data.contacts.map((c, i) => (
              <div key={c.id} className="flex items-center gap-3 border-b border-border px-4 py-2.5 last:border-b-0">
                <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary-subtle text-xs font-semibold text-primary">
                  {initials(c.full_name)}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-2 truncate text-sm font-medium">
                    {c.full_name}
                    {i === 0 && <ToneBadge tone="green">Written to first</ToneBadge>}
                  </p>
                  <p className="truncate text-xs text-fg-muted">
                    {c.title ?? 'No title'}
                    {c.role_label && <span className="text-fg-subtle"> · {c.role_label}</span>}
                  </p>
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
      <div>
        <p className="mb-2 text-xs font-medium text-fg-subtle">Signals (used by cold emails)</p>
        <SignalsPanel companyId={data.id} compact />
      </div>
      <NewContactDialog
        key={`add-${adding}`}
        open={adding}
        title={`Add a contact at ${data.name}`}
        submitLabel="Add contact"
        pending={add.isPending}
        onOpenChange={setAdding}
        onSubmit={(contact) =>
          add.mutate(
            { companyId: data.id, ...contact },
            {
              onSuccess: () => {
                toast.success('Contact added', { description: 'Open jobs here were re-matched.' })
                setAdding(false)
              },
              onError: (e) => toast.error(e.message),
            },
          )
        }
      />
    </div>
  )
}

export function CompaniesTab({ onImport }: { onImport: () => void }) {
  const url = useSearchParamState()
  const [q, setQ] = useState('')
  const [limit, setLimit] = useState(200)
  const filter = (url.get('filter') as CompanyFilter | null) ?? 'with_jobs'
  const { data, isPending, error, refetch } = useCompanies(q, filter, limit)
  const selected = url.get('company') ? Number(url.get('company')) : null
  const companies = useMemo(() => data?.items ?? [], [data])
  const ids = useMemo(() => companies.map((c) => c.id), [companies])

  useEffect(() => {
    const first = companies.find((c) => c.contact_count > 0) ?? companies[0]
    if (selected === null && first && !q) url.set({ company: first.id })
  }, [selected, companies, q, url])

  useListKeyboard({ ids, selectedId: selected, onSelect: (id) => url.set({ company: id }) })
  const clearSelection = useCallback(() => url.set({ company: null }), [url])

  if (!isPending && !error && companies.length === 0 && !q && filter === 'with_jobs') {
    return (
      <EmptyState
        icon={Users}
        title="No companies yet"
        description="Companies appear with discovered jobs and with your Apollo import."
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
      <div data-tour="contacts-companies" className="flex w-[360px] shrink-0 flex-col border-r border-border bg-bg">
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
          <Tabs value={filter} onValueChange={(v) => url.set({ filter: v === 'with_jobs' ? null : v, company: null })}>
            <SegmentedList className="w-full">
              {FILTERS.map((f) => (
                <SegmentedTrigger key={f.value} value={f.value} className="flex-1 px-1.5 text-xs">
                  {f.label}
                </SegmentedTrigger>
              ))}
            </SegmentedList>
          </Tabs>
          <p className="px-0.5 text-2xs text-fg-subtle">{pluralize(data?.total ?? 0, 'company', 'companies')}</p>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {isPending ? (
            <SkeletonRows rows={8} />
          ) : error ? (
            <ErrorState compact error={error} onRetry={() => refetch()} />
          ) : companies.length === 0 ? (
            <EmptyState compact icon={SearchX} title={q ? `No companies match “${q}”` : 'Nothing here'} />
          ) : (
            <>
              {companies.map((c) => (
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
                      {c.best_contact ?? (c.contact_search === 'not_found' ? 'Nobody found' : c.contact_search === 'never' ? 'Never looked up' : 'No contact yet')}
                      {c.open_jobs > 0 && ` · ${pluralize(c.open_jobs, 'open job')}`}
                    </p>
                  </div>
                  {c.contacted_at && (
                    <Tooltip content={`Contacted ${relativeTime(c.contacted_at)}`}>
                      <UserRoundCheck className="size-4 text-warning-dot" />
                    </Tooltip>
                  )}
                </button>
              ))}
              {data && data.total > companies.length && (
                <div className="p-3">
                  <Button size="sm" variant="ghost" className="w-full" onClick={() => setLimit((l) => l + 200)}>
                    Show more ({data.total - companies.length} left)
                  </Button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
      <div data-tour="contacts-detail" className="min-w-0 flex-1 overflow-y-auto">
        {selected !== null ? (
          <CompanyDetailPane key={selected} id={selected} onMissing={clearSelection} />
        ) : (
          <EmptyState icon={Building2} title="Select a company" description="Contacts and jobs for the company appear here." />
        )}
      </div>
    </div>
  )
}
