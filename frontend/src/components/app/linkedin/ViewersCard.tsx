import { Eye, Trash2, UserPlus } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { Section } from '@/components/app/PageHeader'
import { ErrorState } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { pluralize } from '@/lib/format'
import { useAddViewer, useLeads, useRemoveLead } from '@/lib/queries/linkedin'
import type { ViewerResult } from '@/lib/types'

const EMPTY = { full_name: '', title: '', company: '', linkedin_url: '', viewed_on: '' }

/** LinkedIn Premium shows who viewed your profile. Add one here: they become a person in the
 * LinkedIn track with the reason "viewed my profile on <date>", linked to your best open job at
 * their company (or kept as a lead until there is one). Drafts open warmly and never mention it. */
export function ViewersCard() {
  const add = useAddViewer()
  const leads = useLeads()
  const remove = useRemoveLead()
  const [f, setF] = useState(EMPTY)
  const [result, setResult] = useState<ViewerResult | null>(null)
  const ready = f.full_name.trim().length >= 2 && f.company.trim().length >= 1
  return (
    <Section title="Viewed my profile" action={<span className="text-xs text-fg-subtle">Premium</span>}>
      <div className="space-y-3 p-4" data-tour="linkedin-viewers">
        <p className="text-xs text-fg-muted">
          Someone looked at your profile? Add them: they join the LinkedIn track for your best open job at their company. Only you see the reason; the drafts open warmly and never mention the visit.
        </p>
        <form
          className="grid grid-cols-[1fr_1fr_1fr_auto] gap-2 max-lg:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault()
            add.mutate(
              { full_name: f.full_name, title: f.title || null, company: f.company, linkedin_url: f.linkedin_url || null, viewed_on: f.viewed_on || null },
              {
                onSuccess: (r) => {
                  setResult(r)
                  setF(EMPTY)
                  toast.success(r.linked ? `Added for ${r.job?.title} at ${r.company}` : `Saved as a lead: no job at ${r.company} yet`)
                },
                onError: (err) => toast.error(err.message),
              },
            )
          }}
        >
          <Input value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} placeholder="Name" aria-label="Name" />
          <Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="Title" aria-label="Title" />
          <Input value={f.company} onChange={(e) => setF({ ...f, company: e.target.value })} placeholder="Company" aria-label="Company" />
          <Button type="submit" size="md" variant="default" disabled={!ready || add.isPending}>
            <UserPlus />
            Add
          </Button>
          <Input className="col-span-2 max-lg:col-span-1" value={f.linkedin_url} onChange={(e) => setF({ ...f, linkedin_url: e.target.value })} placeholder="Profile URL" aria-label="Profile URL" />
          <Input type="date" value={f.viewed_on} onChange={(e) => setF({ ...f, viewed_on: e.target.value })} aria-label="Viewed on (default today)" title="Viewed on (default today)" />
        </form>

        {result && (
          <p className="rounded-md bg-bg-subtle px-3 py-2 text-xs text-fg-muted" aria-live="polite">
            {result.linked && result.job ? (
              <>
                Added to the LinkedIn track for{' '}
                <Link to={`/jobs/${result.job.job_id}#linkedin`} className="font-medium text-primary hover:underline">
                  {result.job.title}
                </Link>{' '}
                at {result.company}
                {result.job.score != null ? ` (fit ${result.job.score})` : ''}, with the reason “{result.reason}”.
                {result.other_jobs.length > 0 && ` You have ${pluralize(result.other_jobs.length, 'other open job')} there; open one and add them from its LinkedIn section to message about that one instead.`}
              </>
            ) : (
              <>No job at {result.company} in the app yet: saved as a lead below. It links itself to a job there as soon as one exists.</>
            )}
          </p>
        )}

        {leads.isPending ? (
          <Skeleton className="h-10" />
        ) : leads.error ? (
          <ErrorState compact error={leads.error} onRetry={() => void leads.refetch()} />
        ) : leads.data.length === 0 ? (
          <p className="flex items-center gap-2 text-xs text-fg-subtle">
            <Eye className="size-3.5" />
            No leads waiting for a job.
          </p>
        ) : (
          <div>
            <p className="mb-1 text-xs font-medium text-fg-subtle">Waiting for a job at their company</p>
            <ul className="divide-y divide-border rounded-md border border-border">
              {leads.data.map((l) => (
                <li key={l.id} className="flex items-center gap-3 px-3 py-2">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">
                      {l.full_name}
                      {l.title && <span className="font-normal text-fg-muted"> · {l.title}</span>}
                    </p>
                    <p className="truncate text-xs text-fg-muted">
                      {l.company} · {l.reason}
                    </p>
                  </div>
                  {l.linkedin_url && (
                    <Button size="xs" variant="ghost" asChild>
                      <a href={l.linkedin_url} target="_blank" rel="noreferrer">
                        Profile
                      </a>
                    </Button>
                  )}
                  <Button size="icon-sm" variant="ghost" aria-label={`Remove ${l.full_name}`} onClick={() => remove.mutate(l.id, { onError: (e) => toast.error(e.message) })}>
                    <Trash2 />
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Section>
  )
}
