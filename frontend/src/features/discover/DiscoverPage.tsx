import { Compass, Radar, SearchX } from 'lucide-react'
import { useMemo } from 'react'
import { useNavigate } from 'react-router'
import { PageHeader } from '@/components/app/PageHeader'
import { EmptyState, ErrorState, SkeletonRows } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useDiscoveryAction } from '@/hooks/useDiscoveryAction'
import { useHotkeys } from '@/hooks/useHotkeys'
import { useListKeyboard } from '@/hooks/useListKeyboard'
import { useSearchParamState } from '@/hooks/useSearchParamState'
import { useTriageActions } from '@/hooks/useTriageActions'
import { pluralize } from '@/lib/format'
import { type JobFilters, useJobs } from '@/lib/queries/jobs'
import { useNavCounts } from '@/lib/queries/workflow'
import type { JobListItem } from '@/lib/types'
import { FilterBar } from './FilterBar'
import { hasActiveFilters } from './filters'
import { JobPanel } from './JobPanel'
import { JobRow } from './JobRow'

const FILTER_KEYS = ['q', 'source', 'remote', 'country', 'min_score', 'posted_within', 'hide_duplicates']

export default function DiscoverPage() {
  const navigate = useNavigate()
  const url = useSearchParamState()
  const discovery = useDiscoveryAction()
  const counts = useNavCounts()
  const triage = useTriageActions()

  const filters: JobFilters = {
    stage: (url.get('stage') as JobFilters['stage']) ?? 'new',
    q: url.get('q') ?? undefined,
    source: url.getAll('source'),
    remote: url.getAll('remote'),
    country: url.getAll('country'),
    min_score: url.get('min_score') ? Number(url.get('min_score')) : null,
    posted_within: url.get('posted_within') ? Number(url.get('posted_within')) : null,
    hide_duplicates: url.get('hide_duplicates') === '1',
    sort: (url.get('sort') as JobFilters['sort']) ?? 'fit',
  }
  const selectedId = url.get('job') ? Number(url.get('job')) : null
  const { data, isPending, error, refetch } = useJobs(filters)
  // Only asked when the current view is empty: has anything ever been discovered?
  const everything = useJobs({ stage: 'all' }, { enabled: !!data && data.total === 0 })
  const neverDiscovered = everything.data?.total === 0

  // Respect optimistic stage changes so triaged jobs leave the "New" view immediately.
  const items = useMemo(
    () =>
      (data?.items ?? []).filter((j) =>
        filters.stage === 'new'
          ? j.application.stage === 'new'
          : filters.stage === 'open'
            ? j.application.stage !== 'closed'
            : true,
      ),
    [data, filters.stage],
  )
  const ids = useMemo(() => items.map((j) => j.id), [items])

  const select = (id: number | null) => url.set({ job: id })
  const setFilters = (patch: Partial<JobFilters>) => {
    const out: Record<string, string | string[] | null> = {}
    for (const [k, v] of Object.entries(patch)) {
      if (typeof v === 'boolean') out[k] = v ? '1' : null
      else if (typeof v === 'number') out[k] = String(v)
      else out[k] = (v as string | string[] | null) ?? null
    }
    url.set(out)
  }
  const clearFilters = () => url.set(Object.fromEntries(FILTER_KEYS.map((k) => [k, null])))

  const act = (job: JobListItem, action: 'shortlist' | 'dismiss') => {
    const index = ids.indexOf(job.id)
    const next = ids[index + 1] ?? ids[index - 1] ?? null
    const target = { jobId: job.id, title: job.title, company: job.company.name }
    const leavesView = filters.stage === 'new' || (filters.stage === 'open' && action === 'dismiss')
    const advance = () => {
      // Read the live URL: keyboard actions can run before this render's selectedId updates.
      const current = new URLSearchParams(window.location.search).get('job')
      if (leavesView && Number(current) === job.id) select(next)
    }
    if (job.application.stage !== 'new') return
    if (action === 'shortlist') triage.shortlist(target, advance)
    else triage.dismiss(target, advance)
  }
  const byId = (id: number) => items.find((j) => j.id === id)

  useListKeyboard({
    ids,
    selectedId,
    onSelect: select,
    onOpen: (id) => navigate(`/jobs/${id}`),
    actions: {
      s: (id) => byId(id) && act(byId(id)!, 'shortlist'),
      d: (id) => byId(id) && act(byId(id)!, 'dismiss'),
    },
  })
  useHotkeys({ escape: () => select(null) }, { enabled: selectedId !== null })

  const selectedJob = selectedId !== null ? byId(selectedId) : undefined
  const filtered = hasActiveFilters(filters)

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Discover"
        description={
          data
            ? `${pluralize(items.length, 'job')} · ${filters.sort === 'newest' ? 'newest first' : 'best fit first'}`
            : 'Triage newly discovered jobs'
        }
        className="pb-0"
      >
        <Tabs value={filters.stage} onValueChange={(v) => url.set({ stage: v === 'new' ? null : v, job: null })}>
          <TabsList>
            <TabsTrigger value="new" count={counts.data?.discover_new}>
              New
            </TabsTrigger>
            <TabsTrigger value="open">All open</TabsTrigger>
            <TabsTrigger value="all">All</TabsTrigger>
          </TabsList>
        </Tabs>
      </PageHeader>
      <FilterBar filters={filters} onChange={setFilters} onClear={clearFilters} />

      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 overflow-y-auto" role="listbox" aria-label="Jobs">
          {isPending ? (
            <SkeletonRows rows={10} />
          ) : error ? (
            <ErrorState error={error} onRetry={() => refetch()} />
          ) : items.length === 0 ? (
            filtered ? (
              <EmptyState
                icon={SearchX}
                title="No jobs match these filters"
                description="Try widening the filters or clearing them."
                action={<Button size="sm" onClick={clearFilters}>Clear filters</Button>}
              />
            ) : filters.stage === 'new' && !neverDiscovered ? (
              <EmptyState
                icon={Compass}
                title="Inbox zero: every new job is triaged"
                description="New listings arrive with the daily discovery run. You can also pull now."
                action={
                  <Button size="sm" variant="default" onClick={discovery.trigger} disabled={discovery.pending}>
                    <Radar />
                    Run discovery
                  </Button>
                }
              />
            ) : (
              <EmptyState
                icon={Compass}
                title="No jobs yet"
                description="Run discovery to pull listings from your enabled sources. It also runs daily on its own."
                action={
                  <Button size="sm" variant="default" onClick={discovery.trigger} disabled={discovery.pending}>
                    <Radar />
                    Run discovery
                  </Button>
                }
              />
            )
          ) : (
            items.map((job) => (
              <JobRow
                key={job.id}
                job={job}
                selected={job.id === selectedId}
                onSelect={() => select(job.id === selectedId ? null : job.id)}
                onShortlist={() => act(job, 'shortlist')}
                onDismiss={() => act(job, 'dismiss')}
              />
            ))
          )}
        </div>
        {selectedId !== null && (
          <JobPanel
            key={selectedId}
            jobId={selectedId}
            onClose={() => select(null)}
            onShortlist={() => selectedJob && act(selectedJob, 'shortlist')}
            onDismiss={() => selectedJob && act(selectedJob, 'dismiss')}
          />
        )}
      </div>
    </div>
  )
}
