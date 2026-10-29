import { Trash2, Users } from 'lucide-react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { ToneBadge } from '@/components/app/badges'
import { Section } from '@/components/app/PageHeader'
import { EmptyState, ErrorState, SkeletonRows } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { Tooltip } from '@/components/ui/tooltip'
import { relativeTime } from '@/lib/format'
import { useCapturedPeople, useDeleteSnapshot } from '@/lib/queries/linkedin'

const ROLE: Record<string, string> = { recruiter: 'Recruiter', lead: 'Team lead', peer: 'Peer', hiring_team: 'Hiring team' }

/** People saved with the browser extension: the ones on a job, and the ones waiting for a job at their company. */
export function CapturedPeople() {
  const { data, isPending, error, refetch } = useCapturedPeople()
  const forget = useDeleteSnapshot()
  return (
    <Section title="People captured" action={<span className="text-xs text-fg-subtle">{data ? `${data.total}` : ''}</span>}>
      <div data-tour="linkedin-people">
        {isPending ? (
          <SkeletonRows rows={3} />
        ) : error ? (
          <ErrorState compact error={error} onRetry={() => refetch()} />
        ) : data.items.length === 0 ? (
          <EmptyState
            compact
            icon={Users}
            title="Nobody captured yet"
            description="Open someone's LinkedIn profile and press “Save person” in the extension: they're saved here with their role, and join your best open job at their company."
            action={<TourButton tour="linkedin" />}
          />
        ) : (
          <ul>
            {data.items.map((p) => (
              <li key={p.contact_id} className="flex items-center gap-3 border-b border-border px-4 py-2.5 last:border-b-0">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">
                    {p.profile_url ? (
                      <a href={p.profile_url} target="_blank" rel="noreferrer" className="hover:underline">
                        {p.full_name}
                      </a>
                    ) : (
                      p.full_name
                    )}
                  </p>
                  <p className="truncate text-xs text-fg-muted">
                    {p.current_title || p.headline} @ {p.company} · captured {relativeTime(p.captured_at)}
                  </p>
                  <p className="truncate text-xs text-fg-subtle">
                    {p.jobs.length === 0 ? (
                      'Waiting for a job at this company: they join the next one you capture.'
                    ) : (
                      <>
                        On{' '}
                        {p.jobs.map((j, i) => (
                          <span key={j.job_id}>
                            {i > 0 && ', '}
                            <Link to={`/jobs/${j.job_id}`} className="text-primary hover:underline">
                              {j.title}
                            </Link>
                          </span>
                        ))}
                      </>
                    )}
                  </p>
                </div>
                <ToneBadge tone={p.persona === 'recruiter' ? 'slate' : p.persona === 'lead' ? 'blue' : 'gray'} dot={false}>
                  {ROLE[p.persona] ?? p.persona}
                </ToneBadge>
                {p.alumni && <ToneBadge tone="teal">Alumni</ToneBadge>}
                {p.do_not_contact && <ToneBadge tone="red">Do not contact</ToneBadge>}
                <Tooltip content="Forget the captured profile fields. The contact and its messages stay.">
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label={`Delete the captured profile of ${p.full_name}`}
                    onClick={() => forget.mutate(p.contact_id, { onSuccess: () => toast.success('Captured profile deleted'), onError: (e) => toast.error(e.message) })}
                  >
                    <Trash2 />
                  </Button>
                </Tooltip>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Section>
  )
}
