import { Check, Trash2, TriangleAlert, Users } from 'lucide-react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { ToneBadge } from '@/components/app/badges'
import { EmptyState, ErrorState, SkeletonRows } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Select } from '@/components/ui/select'
import { Tooltip } from '@/components/ui/tooltip'
import { relativeTime } from '@/lib/format'
import { useCapturedPeople, useDeleteSnapshot, useEditProfile, useMarkProfileReviewed } from '@/lib/queries/linkedin'
import type { CapturedPerson } from '@/lib/types'

const ROLES = [
  { value: 'recruiter', label: 'Recruiter' },
  { value: 'lead', label: 'Team lead' },
  { value: 'peer', label: 'Peer' },
]

const needsReview = (p: CapturedPerson) => p.flags.length > 0 && !p.reviewed_at

/** People saved with the extension: the role (yours to change), the alumni flag, the jobs they are on or
 * the job they wait for. Anything the capture looked unsure about is flagged and listed first. */
export function CapturedProfiles() {
  const { data, isPending, error, refetch } = useCapturedPeople()
  const forget = useDeleteSnapshot()
  const edit = useEditProfile()
  const reviewed = useMarkProfileReviewed()
  const items = [...(data?.items ?? [])].sort((a, b) => Number(needsReview(b)) - Number(needsReview(a)))
  const fail = (e: Error) => toast.error(e.message)
  return (
    <div data-tour="linkedin-people">
      {isPending ? (
        <SkeletonRows rows={3} />
      ) : error ? (
        <ErrorState compact error={error} onRetry={() => refetch()} />
      ) : items.length === 0 ? (
        <EmptyState
          compact
          icon={Users}
          title="No LinkedIn profiles yet"
          description="Open someone's LinkedIn profile and press “Save profile” in the extension: they're saved here with their role, and join your best open job at their company."
          action={<TourButton tour="linkedin" />}
        />
      ) : (
        <ul>
          {items.map((p) => (
            <li key={p.contact_id} className="border-b border-border last:border-b-0">
              <div className="flex items-center gap-3 px-4 py-2.5">
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
                    {p.current_title || p.headline} @ {p.company} · saved {relativeTime(p.captured_at)}
                  </p>
                  <p className="truncate text-xs text-fg-subtle">
                    {p.jobs.length === 0 ? (
                      'Waiting for a job at this company: they join the next one you save.'
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
                {needsReview(p) && (
                  <ToneBadge tone="amber" dot={false}>
                    Needs review
                  </ToneBadge>
                )}
                {p.do_not_contact && <ToneBadge tone="red">Do not contact</ToneBadge>}
                <Select
                  size="sm"
                  value={p.persona === 'hiring_team' ? 'peer' : p.persona}
                  onValueChange={(persona) => edit.mutate({ contactId: p.contact_id, persona }, { onError: fail })}
                  options={ROLES}
                  aria-label={`Role of ${p.full_name}`}
                />
                <label className="flex items-center gap-1.5 text-xs text-fg-muted">
                  <Checkbox checked={p.alumni} onCheckedChange={(v) => edit.mutate({ contactId: p.contact_id, alumni: v === true }, { onError: fail })} />
                  Alum
                </label>
                <Tooltip content="Forget the captured profile fields. The contact and its messages stay.">
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label={`Delete the captured profile of ${p.full_name}`}
                    onClick={() => forget.mutate(p.contact_id, { onSuccess: () => toast.success('Captured profile deleted'), onError: fail })}
                  >
                    <Trash2 />
                  </Button>
                </Tooltip>
              </div>
              {needsReview(p) && (
                <div className="flex items-start gap-3 bg-warning-bg px-4 py-2 text-xs text-warning-fg">
                  <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
                  <ul className="min-w-0 flex-1 space-y-0.5">
                    {p.flags.map((f) => (
                      <li key={f.code}>{f.text}</li>
                    ))}
                  </ul>
                  <Button size="xs" variant="secondary" onClick={() => reviewed.mutate(p.contact_id, { onError: fail })}>
                    <Check />
                    Looks right
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
