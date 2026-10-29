import { Check, ExternalLink, Search, TriangleAlert } from 'lucide-react'
import { Link } from 'react-router'
import { Section } from '@/components/app/PageHeader'
import { PageHeader } from '@/components/app/PageHeader'
import { EmptyState, ErrorState, SkeletonRows } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Tooltip } from '@/components/ui/tooltip'
import { useSearchParamState } from '@/hooks/useSearchParamState'
import { useCapturedJobs, useCapturedPeople, useLinkedInLinks, useLinkedInSummary, useOpenLink } from '@/lib/queries/linkedin'
import { LinkedInSummaryList } from '@/components/app/linkedin/LinkedInSummaryList'
import { CapturedJobs } from '@/components/app/linkedin/CapturedJobs'
import { CapturedProfiles } from '@/components/app/linkedin/CapturedProfiles'
import { ViewersCard } from '@/components/app/linkedin/ViewersCard'
import { cn } from '@/lib/utils'

/** Today's LinkedIn searches: one per role × country, past 24 hours, newest first. Clicking
 * opens LinkedIn in a new tab and marks the link "opened today" (it resets tomorrow). */
function SearchLinks() {
  const url = useSearchParamState()
  const remote = url.get('remote') === '1'
  const { data, isPending, error, refetch } = useLinkedInLinks(remote)
  const open = useOpenLink()
  return (
    <Section
      title="Today's searches"
      action={
        <span className="flex items-center gap-4 text-xs text-fg-muted">
          <label className="flex items-center gap-1.5">
            <Switch checked={remote} onCheckedChange={(v) => url.set({ remote: v ? '1' : null })} aria-label="Remote only" />
            Remote only
          </label>
          {data && (
            <span className="tabular-nums">
              {data.opened} / {data.total} opened today
            </span>
          )}
        </span>
      }
    >
      <div className="p-4" data-tour="linkedin-searches">
        {isPending ? (
          <SkeletonRows rows={4} />
        ) : error ? (
          <ErrorState compact error={error} onRetry={() => refetch()} />
        ) : data.total === 0 && data.missing_geo.length === 0 ? (
          <EmptyState
            compact
            icon={Search}
            title="No searches yet"
            description="Searches are built from your roles and target countries."
            action={
              <Button size="sm" asChild>
                <Link to="/settings">Add roles and countries</Link>
              </Button>
            }
          />
        ) : (
          <div className="space-y-3">
            {data.missing_geo.length > 0 && (
              <p className="flex items-start gap-2 rounded-md bg-warning-bg px-3 py-2 text-xs text-warning-fg">
                <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
                <span>
                  No LinkedIn location id for {data.missing_geo.map((c) => c.name).join(', ')}: no links there (a text location can land in the wrong place).{' '}
                  <Link to="/settings?section=linkedin" className="font-medium underline-offset-2 hover:underline">
                    Add it in Settings → LinkedIn
                  </Link>
                </span>
              </p>
            )}
            <p className="text-xs text-fg-subtle">Each link is a LinkedIn job search, posted in the past 24 hours, newest first. You browse; the app never visits LinkedIn.</p>
            {data.groups.map((g) => (
              <div key={`${g.track}-${g.role}`} className="flex flex-wrap items-center gap-2">
                <span className="w-56 shrink-0 truncate text-sm font-medium" title={g.track}>
                  {g.role}
                </span>
                {g.links.map((l) => (
                  <Tooltip
                    key={l.key}
                    content={l.verified ? `geoId ${l.geo_id} (confirmed)` : `geoId ${l.geo_id} not confirmed yet: check where it lands, then confirm it in Settings → LinkedIn`}
                  >
                    <a
                      href={l.url}
                      target="_blank"
                      rel="noreferrer"
                      onClick={() => open.mutate(l.key)}
                      className={cn(
                        'inline-flex h-7 items-center gap-1.5 rounded-md border px-2.5 text-xs transition-colors duration-120',
                        l.opened_today ? 'border-border bg-bg-subtle text-fg-subtle' : 'border-border-strong text-fg hover:bg-surface-hover',
                      )}
                    >
                      {l.opened_today ? <Check className="size-3.5 text-success-fg" /> : <ExternalLink className="size-3.5 text-fg-subtle" />}
                      {l.country_name}
                      {!l.verified && <span className="size-1.5 rounded-full bg-warning-dot" aria-label="unverified location" />}
                    </a>
                  </Tooltip>
                ))}
              </div>
            ))}
          </div>
        )}
      </div>
    </Section>
  )
}

function ToDo() {
  const { data, isPending, error, refetch } = useLinkedInSummary()
  return (
    <Section title="To do on LinkedIn">
      <div className="p-2" data-tour="linkedin-todo">
        {isPending ? <SkeletonRows rows={3} /> : error ? <ErrorState compact error={error} onRetry={() => refetch()} /> : <LinkedInSummaryList data={data} />}
      </div>
    </Section>
  )
}

type View = 'today' | 'jobs' | 'profiles'

export default function LinkedInPage() {
  const url = useSearchParamState()
  const raw = url.get('view')
  const view: View = raw === 'jobs' || raw === 'profiles' ? raw : 'today'
  const jobs = useCapturedJobs()
  const people = useCapturedPeople()
  const peopleToReview = (people.data?.items ?? []).filter((p) => p.flags.length > 0 && !p.reviewed_at).length
  const highlight = url.get('job') ? Number(url.get('job')) : null
  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="LinkedIn"
        description="Daily searches built from your roles, the jobs and people you saved with the browser extension, and the people to message. You browse and send; the app builds links and drafts."
      >
        <Tabs data-tour="linkedin-tabs" value={view} onValueChange={(v) => url.set({ view: v === 'today' ? null : v, job: null })}>
          <TabsList>
            <TabsTrigger value="today">Today</TabsTrigger>
            <TabsTrigger value="jobs" count={jobs.data?.total}>
              LinkedIn Jobs{jobs.data && jobs.data.needs_review > 0 ? ` · ${jobs.data.needs_review} to review` : ''}
            </TabsTrigger>
            <TabsTrigger value="profiles" count={people.data?.total}>
              LinkedIn Profiles{peopleToReview > 0 ? ` · ${peopleToReview} to review` : ''}
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </PageHeader>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl space-y-4 px-6 py-5">
          {view === 'today' && (
            <>
              <ToDo />
              <ViewersCard />
              <SearchLinks />
              <Section title="The browser extension">
                <div className="space-y-2 p-4 text-sm text-fg-muted">
                  <p>
                    Open a LinkedIn job or profile and press <strong>Save job</strong> / <strong>Save profile</strong> in the extension: it is saved at once. Jobs wait in LinkedIn Jobs, people in LinkedIn Profiles, and anything that looks misread is flagged for a look.
                  </p>
                  <p className="text-xs text-fg-subtle">
                    Not set up yet?{' '}
                    <Link to="/settings?section=linkedin" className="text-primary hover:underline">
                      Create a token in Settings → LinkedIn
                    </Link>
                    . The old bookmark still works there too.
                  </p>
                </div>
              </Section>
            </>
          )}
          {view === 'jobs' && (
            <Section title="LinkedIn Jobs" action={<span className="text-xs text-fg-subtle">Saved with the extension; New ones wait here, not in Discover</span>}>
              <CapturedJobs highlight={highlight} />
            </Section>
          )}
          {view === 'profiles' && (
            <Section title="LinkedIn Profiles" action={<span className="text-xs text-fg-subtle">Saved with the extension; not mixed into Contacts</span>}>
              <CapturedProfiles />
            </Section>
          )}
        </div>
      </div>
    </div>
  )
}
