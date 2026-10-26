import { ArrowDownWideNarrow, Compass, EyeOff, Radar, SearchX } from 'lucide-react'
import { Fragment } from 'react'
import { toast } from 'sonner'
import { useNavigate } from 'react-router'
import { DiscoveryProgress } from '@/components/app/DiscoveryProgress'
import { ScoringProgress } from '@/components/app/ScoringProgress'
import { PageHeader } from '@/components/app/PageHeader'
import { TourButton } from '@/components/app/tour/TourButton'
import { EmptyState, ErrorState, SkeletonRows } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Tooltip } from '@/components/ui/tooltip'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useDiscoveryAction } from '@/hooks/useDiscoveryAction'
import { useHideScores } from '@/hooks/useHideScores'
import { useHotkeys } from '@/hooks/useHotkeys'
import { useIncrementalList } from '@/hooks/useIncrementalList'
import { useListKeyboard } from '@/hooks/useListKeyboard'
import { usePageLimit } from '@/hooks/usePageLimit'
import { useSearchParamState } from '@/hooks/useSearchParamState'
import { useTriageActions } from '@/hooks/useTriageActions'
import { pluralize } from '@/lib/format'
import { type JobFilters, useJobs, useLabelJob } from '@/lib/queries/jobs'
import { useSearchProfile } from '@/lib/queries/library'
import { useNavCounts } from '@/lib/queries/workflow'
import type { JobListItem, UserLabel } from '@/lib/types'
import { FilterBar } from './FilterBar'
import { hasActiveFilters } from './filters'
import { JobPanel } from './JobPanel'
import { JobRow } from './JobRow'

const FILTER_KEYS = ['q', 'source', 'remote', 'country', 'track', 'min_score', 'posted_within', 'hide_duplicates', 'label', 'flags']

const PAGE = 200

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
    track: url.getAll('track'),
    min_score: url.get('min_score') ? Number(url.get('min_score')) : null,
    posted_within: url.get('posted_within') ? Number(url.get('posted_within')) : null,
    hide_duplicates: url.get('hide_duplicates') === '1',
    label: (url.get('label') as JobFilters['label']) ?? null,
    flags: (url.get('flags') as JobFilters['flags']) ?? null,
    sort: (url.get('sort') as JobFilters['sort']) ?? 'fit',
  }
  const selectedId = url.get('job') ? Number(url.get('job')) : null
  // Blind labeling: nothing that reveals the scorer's opinion (score, fit order, fit filters).
  const [hideScores, setHideScores] = useHideScores()
  const query: JobFilters = hideScores ? { ...filters, sort: 'newest', min_score: null, flags: null } : filters
  // The server sends one page at a time (the best-ranked first); "Load more" asks for the next.
  const { limit, more: loadMore } = usePageLimit(JSON.stringify(query), PAGE)
  const { data, isPending, error, refetch } = useJobs(query, { limit })
  // Only asked when the current view is empty: has anything ever been discovered?
  const everything = useJobs({ stage: 'all', limit: 1 }, { enabled: !!data && data.total === 0 })
  const neverDiscovered = everything.data?.total === 0

  // Respect optimistic stage changes so triaged jobs leave the "New" view immediately.
  const items = (data?.items ?? []).filter((j) =>
    filters.stage === 'new' ? j.application.stage === 'new' : filters.stage === 'open' ? j.application.stage !== 'closed' : true,
  )
  const ids = items.map((j) => j.id)
  // 2,000+ jobs: render 100 at a time (more on scroll, or when j/k or ?job= goes further).
  const { visible, hasMore, remaining, sentinel } = useIncrementalList(items, { mustInclude: selectedId !== null ? ids.indexOf(selectedId) : -1 })

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

  const labelJob = useLabelJob()
  const setLabel = (id: number, label: UserLabel | null) => {
    labelJob.mutate(
      { jobId: id, label },
      { onError: (e) => toast.error(`Couldn't save the label: ${e.message}`) },
    )
  }
  const toggleLabel = (id: number, label: UserLabel) => {
    const job = byId(id)
    if (job) setLabel(id, job.user_label === label ? null : label)
  }
  const profile = useSearchProfile()
  const threshold = profile.data?.min_fit_score ?? null
  const dividerAt =
    query.sort === 'fit' && threshold != null
      ? items.findIndex((j) => j.fit?.score != null && j.fit.score < threshold)
      : -1

  useListKeyboard({
    ids,
    selectedId,
    onSelect: select,
    onOpen: (id) => navigate(`/jobs/${id}`),
    actions: {
      s: (id) => byId(id) && act(byId(id)!, 'shortlist'),
      d: (id) => byId(id) && act(byId(id)!, 'dismiss'),
      '1': (id) => toggleLabel(id, 'good'),
      '2': (id) => toggleLabel(id, 'maybe'),
      '3': (id) => toggleLabel(id, 'no'),
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
            ? `${pluralize(data.total, 'job')} · ${hideScores ? 'newest first, scores hidden' : query.sort === 'newest' ? 'newest first' : 'best fit first'}`
            : 'Triage newly discovered jobs'
        }
        className="pb-0"
        actions={
          <div className="flex items-center gap-4">
            <Tooltip content="Label without seeing scores: hides scores, sorts by newest and turns off fit filters">
              <label className="flex cursor-default items-center gap-2 text-xs text-fg-muted" data-tour="discover-hide-scores">
                <EyeOff className="size-3.5 text-fg-subtle" />
                Hide scores
                <Switch checked={hideScores} onCheckedChange={setHideScores} aria-label="Hide scores while labeling" />
              </label>
            </Tooltip>
            <div className="flex items-center gap-1.5">
              <ArrowDownWideNarrow className="size-3.5 text-fg-subtle" />
              <Select
                size="sm"
                aria-label="Sort"
                value={query.sort ?? 'fit'}
                onValueChange={(v) => setFilters({ sort: v as JobFilters['sort'] })}
                disabled={hideScores}
                options={[
                  { value: 'fit', label: 'Best fit' },
                  { value: 'newest', label: 'Newest' },
                ]}
              />
            </div>
          </div>
        }
      >
        <Tabs data-tour="discover-tabs" value={filters.stage} onValueChange={(v) => url.set({ stage: v === 'new' ? null : v, job: null })}>
          <TabsList>
            <TabsTrigger value="new" count={counts.data?.discover_new}>
              New
            </TabsTrigger>
            <TabsTrigger value="open">All open</TabsTrigger>
            <TabsTrigger value="all">All</TabsTrigger>
          </TabsList>
        </Tabs>
      </PageHeader>
      <DiscoveryProgress />
      <ScoringProgress />
      <FilterBar filters={query} onChange={setFilters} onClear={clearFilters} hideScores={hideScores} />

      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 overflow-y-auto" role="listbox" aria-label="Jobs" data-tour="discover-list">
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
                  <div className="flex gap-2">
                    <Button size="sm" variant="default" onClick={discovery.trigger} disabled={discovery.pending}>
                      <Radar />
                      Run discovery
                    </Button>
                    <TourButton tour="discover" />
                  </div>
                }
              />
            )
          ) : (
            visible.map((job, index) => (
              <Fragment key={job.id}>
                {index === dividerAt && index > 0 && (
                  <div className="flex items-center gap-3 bg-bg-subtle px-6 py-1.5 text-2xs font-medium text-fg-subtle">
                    <span className="h-px flex-1 bg-border" />
                    Below your shortlist threshold ({threshold})
                    <span className="h-px flex-1 bg-border" />
                  </div>
                )}
                <JobRow
                  job={job}
                  selected={job.id === selectedId}
                  onSelect={() => select(job.id === selectedId ? null : job.id)}
                  onShortlist={() => act(job, 'shortlist')}
                  onDismiss={() => act(job, 'dismiss')}
                  hideScore={hideScores}
                />
              </Fragment>
            ))
          )}
          {!hasMore && data && data.total > (data.items.length ?? 0) && (
            <div className="px-6 py-3 text-center">
              <Button size="sm" variant="secondary" onClick={loadMore}>
                Load {Math.min(PAGE, data.total - data.items.length)} more ({data.total - data.items.length} not shown)
              </Button>
            </div>
          )}
          {hasMore && (
            <div ref={sentinel} className="px-6 py-3 text-center text-xs text-fg-subtle" aria-live="polite">
              Loading {pluralize(Math.min(100, remaining), 'more job')}…
            </div>
          )}
        </div>
        {selectedId !== null && (
          <JobPanel
            key={selectedId}
            jobId={selectedId}
            onClose={() => select(null)}
            onShortlist={() => selectedJob && act(selectedJob, 'shortlist')}
            onDismiss={() => selectedJob && act(selectedJob, 'dismiss')}
            onLabel={(label) => setLabel(selectedId, label)}
            hideScores={hideScores}
          />
        )}
      </div>
    </div>
  )
}
